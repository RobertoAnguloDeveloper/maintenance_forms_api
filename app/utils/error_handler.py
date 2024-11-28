# app/utils/error_handler.py

from flask import jsonify
from werkzeug.exceptions import HTTPException

class APIError(Exception):
    def __init__(self, message, status_code=400, payload=None):
        super().__init__()
        self.message = message
        self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        rv['status'] = 'error'
        return rv

def handle_api_error(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response