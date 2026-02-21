import os
from flask import Flask
from dotenv import load_dotenv
from flask_migrate import Migrate
from models import db, Channel
from auth import auth, seed_default_user
from views import views
from api import api


load_dotenv()


def create_app():
    app = Flask(__name__)

    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///club.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)


    # Register blueprints
    app.register_blueprint(auth)
    app.register_blueprint(views)
    app.register_blueprint(api, url_prefix='/api')

    # Create tables & seed
    with app.app_context():
        db.create_all()
        print('✓ Database tables created')
        seed_default_user()

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
