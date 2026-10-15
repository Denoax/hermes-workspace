"""Small operator-only text admission contract. No prompts, paths or tools."""
import re

OPERATIONS = {'chat_admit', 'chat_heartbeat', 'chat_release', 'chat_cancel'}


def request(operation, job_id, arm=None):
    if operation not in OPERATIONS or type(job_id) is not str or not re.fullmatch('[0-9a-f]{32}', job_id):
        raise ValueError('invalid_text_admission')
    result = {'operation': operation, 'job_id': job_id}
    if operation == 'chat_admit':
        if arm not in ('normal', 'abliterated'):
            raise ValueError('unknown_local_model')
        result['arm'] = arm
    elif arm is not None:
        raise ValueError('unexpected_text_model')
    return result
