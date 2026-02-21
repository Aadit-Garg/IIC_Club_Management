from functools import wraps
from flask import session, redirect, url_for, flash, abort
from models import User, db


def get_current_user():
    """Get the currently logged-in user from session."""
    user_id = session.get('user_id')
    if user_id:
        return User.query.get(user_id)
    return None


def login_required(f):
    """Decorator to require login for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(min_role):
    """Decorator to require a minimum role level.
    Hierarchy: jsec (3) > coordinator (2) > member (1)
    """
    role_levels = {'member': 1, 'coordinator': 2, 'jsec': 3}

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login'))
            user = User.query.get(session['user_id'])
            if not user:
                flash('User not found.', 'error')
                return redirect(url_for('auth.login'))
            if user.role_level() < role_levels.get(min_role, 0):
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def generate_unique_id():
    """Generate the next unique member ID (IIC-0001 format)."""
    last_user = User.query.order_by(User.id.desc()).first()
    if last_user:
        try:
            last_num = int(last_user.unique_id.split('-')[1])
        except (IndexError, ValueError):
            last_num = 0
        return f'IIC-{last_num + 1:04d}'
    return 'IIC-0001'


AVATAR_COLORS = [
    '#6C63FF', '#FF6584', '#43E97B', '#F9A826',
    '#00C9FF', '#FF6B6B', '#A78BFA', '#34D399',
    '#F472B6', '#60A5FA', '#FBBF24', '#10B981',
]


def get_random_color():
    """Get a random avatar color."""
    import random
    return random.choice(AVATAR_COLORS)
