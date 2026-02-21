from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


# ─── Channel membership ───
class ChannelMember(db.Model):
    __tablename__ = 'channel_members'

    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey('channels.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    added_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Settings
    is_muted = db.Column(db.Boolean, default=False)
    is_pinned = db.Column(db.Boolean, default=False)
    is_archived = db.Column(db.Boolean, default=False)

    __table_args__ = (db.UniqueConstraint('channel_id', 'user_id'),)

    user = db.relationship('User', foreign_keys=[user_id], back_populates='channel_memberships')
    adder = db.relationship('User', foreign_keys=[added_by])


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(20), unique=True, nullable=False)  # IIC-0001
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='member')  # jsec, coordinator, member
    
    # Profile
    expertise = db.Column(db.String(255), default='')
    current_work = db.Column(db.String(255), default='')
    bio = db.Column(db.Text, default='')
    avatar_color = db.Column(db.String(7), default='#6C63FF')
    
    # Status
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    is_online = db.Column(db.Boolean, default=False)
    has_seen_tour = db.Column(db.Boolean, default=False)

    # Relationships
    messages = db.relationship('Message', backref='author', lazy=True)
    resources = db.relationship('Resource', backref='shared_by', lazy=True)
    tasks_created = db.relationship('Task', foreign_keys='Task.created_by', backref='creator', lazy=True)
    events_created = db.relationship('Event', backref='creator', lazy=True)
    channel_memberships = db.relationship('ChannelMember', foreign_keys='ChannelMember.user_id', back_populates='user', lazy=True, cascade="all, delete-orphan")

    def role_level(self):
        levels = {'jsec': 3, 'coordinator': 2, 'member': 1}
        return levels.get(self.role, 0)

    def can_manage_members(self):
        return self.role == 'jsec'

    def can_assign_work(self):
        return self.role in ('jsec', 'coordinator')

    def can_manage_calendar(self):
        return self.role in ('jsec', 'coordinator')


class Channel(db.Model):
    __tablename__ = 'channels'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), default='')
    channel_type = db.Column(db.String(10), default='group')  # 'group' or 'dm'
    is_private = db.Column(db.Boolean, default=False) # True = Invite only
    min_role_level = db.Column(db.Integer, default=1)  # 1=Member, 2=Coordinator, 3=JSec
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    messages = db.relationship('Message', backref='channel', lazy=True, cascade="all, delete-orphan")
    members = db.relationship('ChannelMember', backref='channel', lazy=True, cascade="all, delete-orphan")


class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey('channels.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), default='text')  # text, task_ref, system
    is_system_message = db.Column(db.Boolean, default=False)
    
    referenced_task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='SET NULL'), nullable=True)
    reply_to_id = db.Column(db.Integer, db.ForeignKey('messages.id', ondelete='SET NULL'), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    referenced_task = db.relationship('Task', foreign_keys=[referenced_task_id], backref='chat_references')
    replies = db.relationship('Message', backref=db.backref('parent', remote_side=[id]), lazy=True)


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id', ondelete='CASCADE'), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='notifications')
    message = db.relationship('Message', backref='notifications')


class Resource(db.Model):
    __tablename__ = 'resources'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    resource_type = db.Column(db.String(20), nullable=False, default='link')  # ppt, sheet, link, other
    description = db.Column(db.Text, default='')
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)

    event = db.relationship('Event', backref='resources', foreign_keys=[event_id])
    task = db.relationship('Task', backref='resources', foreign_keys=[task_id])


class Event(db.Model):
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    event_date = db.Column(db.Date, nullable=False)
    event_time = db.Column(db.String(10), default='')
    location = db.Column(db.String(200), default='')
    mom = db.Column(db.Text, default='')  # Minutes of Meeting
    attendance_code = db.Column(db.String(20), default='')  # For self check-in
    event_type = db.Column(db.String(20), default='event')  # event, meeting
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Task(db.Model):
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    
    # Configuration
    is_open = db.Column(db.Boolean, default=False)  # True = anyone can claim
    max_participants = db.Column(db.Integer, nullable=True)  # Max claimers for open tasks
    priority = db.Column(db.String(10), default='medium') # low, medium, high
    tags = db.Column(db.String(255), default='') # comma separated tags
    
    status = db.Column(db.String(20), default='pending')  # pending, in-progress, review, done
    due_date = db.Column(db.Date, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Submission
    submission_link = db.Column(db.String(500), default='')
    submission_notes = db.Column(db.Text, default='')

    # Many-to-many assignees
    assignees = db.relationship('TaskAssignee', backref='task', lazy=True, cascade="all, delete-orphan")

    def assignee_users(self):
        """Return list of User objects assigned to this task."""
        return [ta.user_id for ta in self.assignees]

    def assignee_list(self):
        """Return list of User objects."""
        return [User.query.get(ta.user_id) for ta in self.assignees]


class TaskAssignee(db.Model):
    __tablename__ = 'task_assignees'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='assigned_tasks')
    
    __table_args__ = (db.UniqueConstraint('task_id', 'user_id'),)


class TaskAuditLog(db.Model):
    __tablename__ = 'task_audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False) # created, assigned, claimed, status_change, etc.
    details = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='task_logs')
    task = db.relationship('Task', backref='logs')


# ─── Polls ───
class Poll(db.Model):
    __tablename__ = 'polls'

    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey('channels.id', ondelete='CASCADE'), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id', ondelete='CASCADE'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    question = db.Column(db.String(300), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    options = db.relationship('PollOption', backref='poll', lazy=True, cascade="all, delete-orphan")
    creator = db.relationship('User', foreign_keys=[created_by])


class PollOption(db.Model):
    __tablename__ = 'poll_options'

    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('polls.id', ondelete='CASCADE'), nullable=False)
    text = db.Column(db.String(200), nullable=False)
    sort_order = db.Column(db.Integer, default=0)

    votes = db.relationship('PollVote', backref='option', lazy=True, cascade="all, delete-orphan")


class PollVote(db.Model):
    __tablename__ = 'poll_votes'

    id = db.Column(db.Integer, primary_key=True)
    option_id = db.Column(db.Integer, db.ForeignKey('poll_options.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    voted_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='poll_votes')

    __table_args__ = (db.UniqueConstraint('option_id', 'user_id'),)


# ─── Message Reactions ───
class MessageReaction(db.Model):
    __tablename__ = 'message_reactions'

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    emoji = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('message_id', 'user_id', 'emoji'),)


# ─── Sheets ───
class Sheet(db.Model):
    __tablename__ = 'sheets'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    channel_id = db.Column(db.Integer, db.ForeignKey('channels.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    creator = db.relationship('User', backref='sheets')
    channel = db.relationship('Channel', backref='sheets')
    cells = db.relationship('SheetCell', backref='sheet', lazy=True, cascade="all, delete-orphan")

class SheetCell(db.Model):
    __tablename__ = 'sheet_cells'
    id = db.Column(db.Integer, primary_key=True)
    sheet_id = db.Column(db.Integer, db.ForeignKey('sheets.id', ondelete='CASCADE'), nullable=False)
    row = db.Column(db.Integer, nullable=False)
    col = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, default='')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('sheet_id', 'row', 'col'),)


# ─── Achievements ───
class Achievement(db.Model):
    __tablename__ = 'achievements'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    category = db.Column(db.String(50), default='general')  # general, hackathon, project, leadership, etc.
    icon = db.Column(db.String(10), default='🏆')
    
    awarded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', foreign_keys=[user_id], backref='achievements')
    awarder = db.relationship('User', foreign_keys=[awarded_by])
    approver = db.relationship('User', foreign_keys=[approved_by])


# ─── Attendance ───
class Attendance(db.Model):
    __tablename__ = 'attendance'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.String(20), default='present')  # present, absent, excused
    notes = db.Column(db.Text, default='')
    marked_at = db.Column(db.DateTime, default=datetime.utcnow)

    event = db.relationship('Event', backref='attendance_records')
    user = db.relationship('User', backref='attendance_records')
    
    __table_args__ = (db.UniqueConstraint('event_id', 'user_id'),)


# ─── Inventory ───
class InventoryItem(db.Model):
    __tablename__ = 'inventory_items'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    total_qty = db.Column(db.Integer, default=1)
    available_qty = db.Column(db.Integer, default=1)
    location = db.Column(db.String(200), default='')
    image_url = db.Column(db.String(500), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class InventoryRequest(db.Model):
    __tablename__ = 'inventory_requests'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('inventory_items.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected, returned, overdue
    request_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    return_date = db.Column(db.Date, nullable=True)
    reason = db.Column(db.Text, default='')
    
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    returned_at = db.Column(db.DateTime, nullable=True)

    item = db.relationship('InventoryItem', backref='requests')
    user = db.relationship('User', foreign_keys=[user_id], backref='inventory_requests')
    approver = db.relationship('User', foreign_keys=[approved_by])


# ─── Wiki ───
class WikiPage(db.Model):
    __tablename__ = 'wiki_pages'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, default='')
    category = db.Column(db.String(100), default='General')
    
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    updater = db.relationship('User', backref='wiki_edits')
