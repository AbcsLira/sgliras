"""Transações repetíveis sem duplicar gravações após uma falha de rede."""
from contextlib import closing
from datetime import datetime
import hashlib
import json
from flask import abort, request, session
from .database import get_db
from .validation import ValidationError, text


def run_operation(payload, callback):
    operation_id = text(payload.get('operacao_id'), 'Identificador da operação')
    if len(operation_id) > 128:
        raise ValidationError('Identificador da operação muito longo.')
    try:
        canonical = json.dumps({k: v for k, v in payload.items() if k != 'operacao_id'},
                               sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError):
        raise ValidationError('A operação contém valores inválidos.') from None
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    # Reserve the writer before reading the key: concurrent retries cannot both apply.
    with closing(get_db()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        saved = db.execute('SELECT * FROM operacoes_idempotentes WHERE operacao_id=?',
                           (operation_id,)).fetchone()
        if saved:
            if (saved['usuario_id'] != session['usuario_id'] or saved['rota'] != request.path
                    or saved['payload_hash'] != digest):
                abort(409, description='Este identificador já foi usado para outra operação.')
            return json.loads(saved['resposta']), 200
        result = callback(db)
        db.execute('''INSERT INTO operacoes_idempotentes
                      (operacao_id,usuario_id,rota,payload_hash,resposta,criado_em)
                      VALUES (?,?,?,?,?,?)''',
                   (operation_id, session['usuario_id'], request.path, digest,
                    json.dumps(result, allow_nan=False), datetime.now().isoformat()))
        return result, 201
