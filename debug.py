from app import app, session, current_user
from flask import session
from flask_login import current_user

with app.app_context():
    print(session)  # Check if session data is stored
    print(current_user.is_authenticated)  # Should be True after login