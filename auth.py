from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Channel, ChannelMember
from helpers import get_current_user, generate_unique_id, get_random_color

auth = Blueprint('auth', __name__)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('views.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['user_role'] = user.role
            session['user_name'] = user.name
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(url_for('views.dashboard'))
        else:
            flash('Invalid email or password.', 'error')

    return render_template('login.html')


@auth.route('/change-password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json() or {}
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    if not current_password or not new_password:
        return jsonify({'error': 'Missing fields'}), 400
        
    user = User.query.get(session['user_id'])
    if not check_password_hash(user.password_hash, current_password):
        return jsonify({'error': 'Incorrect current password'}), 400
        
    try:
        user.password_hash = generate_password_hash(new_password)
        db.session.add(user) # Explicitly mark as modified
        db.session.commit()
        print(f"✓ [AUTH] Password successfully updated for user: {user.email}")
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        print(f"✗ [AUTH] Error updating password: {e}")
        return jsonify({'error': 'Database error occurred'}), 500


@auth.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


def seed_default_user():
    """Create a default JSec user if no users exist."""
    if User.query.count() == 0:
        default_user = User(
            unique_id='IIC-0001',
            name='Admin JSec',
            email='admin@iic.club',
            password_hash=generate_password_hash('admin123'),
            role='jsec',
            expertise='Administration, Management',
            current_work='Setting up the club',
            bio='Default administrator account for IIC Club.',
            avatar_color='#6C63FF'
        )
        db.session.add(default_user)
        db.session.commit()
        print('✓ Default JSec user created: admin@iic.club / admin123')

    # Seed default General channel with admin as member
    if Channel.query.count() == 0:
        admin = User.query.filter_by(email='admin@iic.club').first()
        if admin:
            general = Channel(
                name='General',
                description='General club discussion — everyone is added here',
                channel_type='group',
                min_role_level=1,
                created_by=admin.id
            )
            db.session.add(general)
            db.session.flush()  # get general.id

            # Add admin as member
            membership = ChannelMember(
                channel_id=general.id,
                user_id=admin.id,
                added_by=admin.id
            )
            db.session.add(membership)
            db.session.commit()
            print('✓ Default channel created: #General (admin added as member)')
