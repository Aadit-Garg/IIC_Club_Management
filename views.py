from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort, jsonify
from datetime import datetime, date
from models import db, User, Message, Resource, Event, Task, Channel, ChannelMember, TaskAssignee, Sheet, Notification, Achievement, Attendance
from helpers import login_required, role_required, get_current_user, generate_unique_id, get_random_color
from werkzeug.security import generate_password_hash
import calendar as cal
from services import AnalyticsService

views = Blueprint('views', __name__)


# ─── Context processor ───
@views.app_context_processor
def inject_user():
    user = get_current_user()
    return dict(current_user=user)


# ═══════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════

@views.route('/')
@login_required
def index():
    return redirect(url_for('views.dashboard'))


@views.route('/dashboard')
@login_required
def dashboard():
    user = get_current_user()
    my_tasks = Task.query.join(TaskAssignee).filter(TaskAssignee.user_id == user.id).order_by(Task.created_at.desc()).all()
    upcoming_events = Event.query.filter(Event.event_date >= date.today()).order_by(Event.event_date).limit(5).all()
    recent_messages = Message.query.order_by(Message.created_at.desc()).limit(5).all()
    recent_resources = Resource.query.order_by(Resource.created_at.desc()).limit(5).all()
    total_members = User.query.count()

    return render_template('dashboard.html',
                           user=user,
                           my_tasks=my_tasks,
                           upcoming_events=upcoming_events,
                           recent_messages=recent_messages,
                           recent_resources=recent_resources,
                           total_members=total_members,
                           today=date.today())


@views.route('/dashboard/update', methods=['POST'])
@login_required
def update_profile():
    user = get_current_user()
    user.expertise = request.form.get('expertise', user.expertise)
    user.current_work = request.form.get('current_work', user.current_work)
    user.bio = request.form.get('bio', user.bio)
    user.name = request.form.get('name', user.name)
    db.session.commit()
    flash('Profile updated successfully!', 'success')
    return redirect(url_for('views.dashboard'))


@views.route('/analytics')
@login_required
@role_required('coordinator') # JSec and Coordinator
def analytics():
    productivity = AnalyticsService.get_productivity_stats()
    engagement = AnalyticsService.get_engagement_stats()
    workload = AnalyticsService.get_workload_heatmap()
    attendance = AnalyticsService.get_attendance_stats()
    
    return render_template('analytics.html', 
                           productivity=productivity,
                           engagement=engagement,
                           workload=workload,
                           attendance=attendance)


# ═══════════════════════════════════════════════════
# MEMBERS
# ═══════════════════════════════════════════════════

@views.route('/members')
@login_required
def members():
    search = request.args.get('q', '').strip()
    role_filter = request.args.get('role', '')
    query = User.query

    if search:
        query = query.filter(User.name.contains(search) | User.email.contains(search))
    if role_filter:
        query = query.filter_by(role=role_filter)

    all_members = query.order_by(User.name).all()
    return render_template('members.html', members=all_members, search=search, role_filter=role_filter)


@views.route('/members/add', methods=['POST'])
@role_required('jsec')
def add_member():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    role = request.form.get('role', 'member')
    password = request.form.get('password', 'member123')

    if not name or not email:
        flash('Name and email are required.', 'error')
        return redirect(url_for('views.members'))

    if User.query.filter_by(email=email).first():
        flash('Email already exists.', 'error')
        return redirect(url_for('views.members'))

    if role not in ('jsec', 'coordinator', 'member'):
        role = 'member'

    unique_id = generate_unique_id()
    new_user = User(
        unique_id=unique_id,
        name=name,
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
        avatar_color=get_random_color()
    )
    db.session.add(new_user)
    db.session.flush()

    # Auto-add to General channel
    general = Channel.query.filter_by(name='General', channel_type='group').first()
    if general:
        membership = ChannelMember(channel_id=general.id, user_id=new_user.id, added_by=get_current_user().id)
        db.session.add(membership)

    db.session.commit()
    flash(f'Member {name} ({unique_id}) added!', 'success')
    return redirect(url_for('views.members'))


@views.route('/members/<int:member_id>')
@login_required
def member_profile(member_id):
    member = User.query.get_or_404(member_id)
    task_ids = [ta.task_id for ta in TaskAssignee.query.filter_by(user_id=member.id).all()]
    member_tasks = Task.query.filter(Task.id.in_(task_ids)).all() if task_ids else []
    
    # Task stats
    task_stats = {
        'total': len(member_tasks),
        'done': sum(1 for t in member_tasks if t.status == 'done'),
        'in_progress': sum(1 for t in member_tasks if t.status == 'in-progress'),
        'pending': sum(1 for t in member_tasks if t.status == 'pending'),
    }
    
    # Achievements
    approved_achievements = Achievement.query.filter_by(user_id=member.id, status='approved').order_by(Achievement.created_at.desc()).all()
    pending_achievements = Achievement.query.filter_by(user_id=member.id, status='pending').order_by(Achievement.created_at.desc()).all()
    
    # Get Analytics Stats
    stats = AnalyticsService.get_member_stats(member.id)
    
    return render_template('member_profile.html',
        member=member, member_tasks=member_tasks, task_stats=task_stats,
        approved_achievements=approved_achievements,
        pending_achievements=pending_achievements,
        stats=stats
    )


@views.route('/members/<int:member_id>/edit', methods=['POST'])
@role_required('jsec')
def edit_member(member_id):
    member = User.query.get_or_404(member_id)
    member.name = request.form.get('name', member.name)
    member.email = request.form.get('email', member.email)
    member.role = request.form.get('role', member.role)
    member.expertise = request.form.get('expertise', member.expertise)
    member.current_work = request.form.get('current_work', member.current_work)
    member.bio = request.form.get('bio', member.bio)
    db.session.commit()
    flash(f'{member.name} updated.', 'success')
    return redirect(url_for('views.member_profile', member_id=member.id))


@views.route('/members/<int:member_id>/delete', methods=['POST'])
@role_required('jsec')
def delete_member(member_id):
    member = User.query.get_or_404(member_id)
    user = get_current_user()
    if member.id == user.id:
        flash('You cannot delete yourself.', 'error')
        return redirect(url_for('views.members'))
    db.session.delete(member)
    db.session.commit()
    flash(f'{member.name} has been removed.', 'success')
    return redirect(url_for('views.members'))


# ═══════════════════════════════════════════════════
# DISCUSSION / CHANNELS
# ═══════════════════════════════════════════════════

def user_channels(user):
    """Get all channels a user has access to (member of, or DM participant)."""
    member_channel_ids = [cm.channel_id for cm in ChannelMember.query.filter_by(user_id=user.id).all()]
    return Channel.query.filter(Channel.id.in_(member_channel_ids)).order_by(Channel.created_at.asc()).all()

def get_dm_channels(user):
    """Get DM channels for a user."""
    member_channel_ids = [cm.channel_id for cm in ChannelMember.query.filter_by(user_id=user.id).all()]
    return Channel.query.filter(Channel.id.in_(member_channel_ids), Channel.channel_type == 'dm').all()


@views.route('/discussion', methods=['GET', 'POST'])
@views.route('/chat/<int:channel_id>', methods=['GET', 'POST'])
@login_required
def discussion(channel_id=None):
    user = get_current_user()

    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        channel_id = request.form.get('channel_id', type=int)
        message_type = request.form.get('message_type', 'text')
        referenced_task_id = request.form.get('referenced_task_id', type=int)

        if content and channel_id:
            is_member = ChannelMember.query.filter_by(channel_id=channel_id, user_id=user.id).first()
            if is_member:
                msg = Message(
                    user_id=user.id,
                    content=content,
                    channel_id=channel_id,
                    message_type=message_type,
                    referenced_task_id=referenced_task_id
                )
                db.session.add(msg)
                db.session.commit()
            else:
                flash('You are not a member of this channel.', 'error')

        return redirect(url_for('views.discussion', channel_id=channel_id))

    group_channels = [c for c in user_channels(user) if c.channel_type == 'group']
    dm_channels = get_dm_channels(user)

    if channel_id is None:
        channel_id = request.args.get('channel_id', type=int)

    current_channel = None
    if channel_id:
        current_channel = Channel.query.get(channel_id)
        if current_channel:
            is_member = ChannelMember.query.filter_by(channel_id=current_channel.id, user_id=user.id).first()
            if not is_member:
                flash('Access denied.', 'error')
                current_channel = None

    # Don't auto-select a channel — let the channel list page render
    # (especially important for WhatsApp-style mobile layout)

    messages = []
    channel_members_list = []
    current_channel_member = None
    if current_channel:
        messages = Message.query.filter_by(channel_id=current_channel.id).order_by(Message.created_at.asc()).all()
        channel_members_list = ChannelMember.query.filter_by(channel_id=current_channel.id).all()
        current_channel_member = ChannelMember.query.filter_by(channel_id=current_channel.id, user_id=user.id).first()

    dm_display = []
    for dm_ch in dm_channels:
        other_member = ChannelMember.query.filter(ChannelMember.channel_id == dm_ch.id, ChannelMember.user_id != user.id).first()
        if other_member:
            other_user = User.query.get(other_member.user_id)
            dm_display.append({'channel': dm_ch, 'other_user': other_user})

    all_members = User.query.order_by(User.name).all()

    return render_template('discussion.html',
                           channels=group_channels,
                           dm_channels=dm_display,
                           current_channel=current_channel,
                           messages=messages,
                           channel_members=channel_members_list,
                           current_channel_member=current_channel_member,
                           all_members=all_members)


@views.route('/discussion/create_channel', methods=['POST'])
@login_required
def create_channel():
    user = get_current_user()
    
    # Permission check: Only JSec or Coordinators can create channels
    if user.role_level() < 2:  # 1=member, 2=coordinator, 3=jsec
        flash('Only Coordinators and JSecs can create groups.', 'error')
        return redirect(url_for('views.discussion'))

    name = request.form.get('name')
    description = request.form.get('description')
    min_role_level = request.form.get('min_role_level', type=int)

    if name:
        new_channel = Channel(
            name=name,
            description=description,
            channel_type='group',
            is_private=False,
            created_by=user.id,
            min_role_level=min_role_level
        )
        db.session.add(new_channel)
        db.session.flush()

        # Add creator as member
        membership = ChannelMember(channel_id=new_channel.id, user_id=user.id, added_by=user.id)
        db.session.add(membership)
        db.session.commit()

        flash(f'Channel "#{name}" created!', 'success')
        return redirect(url_for('views.discussion', channel_id=new_channel.id))
    
    flash('Channel name required', 'error')
    return redirect(url_for('views.discussion'))

@views.route('/channels/<int:channel_id>/add_member', methods=['POST'])
@login_required
def add_channel_member(channel_id):
    channel = Channel.query.get_or_404(channel_id)
    user = get_current_user()
    
    # Allow any member to add others? Or restrict? 
    # For now, let's allow any member to add to public groups to encourage growth, 
    # but maybe restrict for private groups (not fully implemented yet).
    if not ChannelMember.query.filter_by(channel_id=channel.id, user_id=user.id).first():
        flash('Permission denied', 'error')
        return redirect(url_for('views.discussion', channel_id=channel.id))

    username = request.form.get('username')
    role = request.form.get('role')
    
    if role:
        # Add all users with this role
        targets = []
        if role == 'all':
            targets = User.query.all()
        else:
            targets = User.query.filter_by(role=role).all()
            
        count = 0
        for t in targets:
             if not ChannelMember.query.filter_by(channel_id=channel.id, user_id=t.id).first():
                 db.session.add(ChannelMember(channel_id=channel.id, user_id=t.id, added_by=user.id))
                 count += 1
        db.session.commit()
        flash(f'Added {count} members (Role: {role}).', 'success')
        
    elif username:
        target_user = User.query.filter_by(name=username).first()
        if target_user:
            if not ChannelMember.query.filter_by(channel_id=channel.id, user_id=target_user.id).first():
                new_member = ChannelMember(channel_id=channel.id, user_id=target_user.id, added_by=user.id)
                db.session.add(new_member)
                db.session.commit()
                flash(f'{target_user.name} added to channel', 'success')
            else:
                flash(f'{target_user.name} is already a member', 'info')
        else:
            flash('User not found', 'error')
    
    return redirect(url_for('views.discussion', channel_id=channel.id))

@views.route('/channels/<int:channel_id>/remove_member', methods=['POST'])
@login_required
def remove_channel_member(channel_id):
    channel = Channel.query.get_or_404(channel_id)
    user = get_current_user()
    
    # Permission: Admin (JSec/Coord) OR Channel Creator
    is_admin = user.role_level() >= 2
    is_creator = channel.created_by == user.id
    
    if not (is_admin or is_creator):
         flash('Only Admins or the Group Creator can remove members.', 'error')
         return redirect(url_for('views.discussion', channel_id=channel.id))

    target_user_id = request.form.get('user_id', type=int)
    if target_user_id:
        if target_user_id == user.id:
            flash('Use the "Leave" button to remove yourself.', 'error')
        else:
            member = ChannelMember.query.filter_by(channel_id=channel.id, user_id=target_user_id).first()
            if member:
                # Prevent removing the creator?
                if member.user_id == channel.created_by:
                     flash('Cannot remove the channel creator.', 'error')
                else:
                    db.session.delete(member)
                    db.session.commit()
                    flash('Member removed', 'success')
            else:
                flash('Member not found', 'error')

    return redirect(url_for('views.discussion', channel_id=channel.id))


@views.route('/discussion/channel/<int:channel_id>/leave', methods=['POST'])
@login_required
def leave_channel(channel_id):
    user = get_current_user()
    membership = ChannelMember.query.filter_by(channel_id=channel_id, user_id=user.id).first()
    if membership:
        db.session.delete(membership)
        db.session.commit()
        flash('You left the group.', 'success')
    return redirect(url_for('views.discussion'))
    
@views.route('/discussion/channel/<int:channel_id>/join', methods=['POST'])
@login_required
def join_channel(channel_id):
    user = get_current_user()
    channel = Channel.query.get_or_404(channel_id)
    
    if channel.is_private:
         flash('This channel is private. You must be added by a member.', 'error')
         return redirect(url_for('views.discussion'))

    existing = ChannelMember.query.filter_by(channel_id=channel_id, user_id=user.id).first()
    if not existing:
        membership = ChannelMember(channel_id=channel_id, user_id=user.id, added_by=user.id)
        db.session.add(membership)
        db.session.commit()
        flash(f'Joined #{channel.name}!', 'success')
    
    return redirect(url_for('views.discussion', channel_id=channel_id))


@views.route('/dm/<int:target_user_id>')
@login_required
def open_dm(target_user_id):
    user = get_current_user()
    target = User.query.get_or_404(target_user_id)

    if user.id == target.id:
        flash('Cannot DM yourself.', 'error')
        return redirect(url_for('views.discussion'))

    user_dm_ids = [cm.channel_id for cm in ChannelMember.query.filter_by(user_id=user.id).all()]
    target_dm_ids = [cm.channel_id for cm in ChannelMember.query.filter_by(user_id=target.id).all()]
    common_ids = set(user_dm_ids) & set(target_dm_ids)

    dm_channel = None
    for cid in common_ids:
        ch = Channel.query.get(cid)
        if ch and ch.channel_type == 'dm':
            dm_channel = ch
            break

    if not dm_channel:
        dm_channel = Channel(
            name=f'DM-{user.id}-{target.id}',
            channel_type='dm',
            created_by=user.id,
            is_private=True
        )
        db.session.add(dm_channel)
        db.session.flush()
        db.session.add(ChannelMember(channel_id=dm_channel.id, user_id=user.id, added_by=user.id))
        db.session.add(ChannelMember(channel_id=dm_channel.id, user_id=target.id, added_by=user.id))
        db.session.commit()

    return redirect(url_for('views.discussion', channel_id=dm_channel.id))


@views.route('/discussion/<int:msg_id>/delete', methods=['POST'])
@role_required('jsec')
def delete_message(msg_id):
    msg = Message.query.get_or_404(msg_id)
    db.session.delete(msg)
    db.session.commit()
    flash('Message deleted.', 'success')
    return redirect(url_for('views.discussion', channel_id=msg.channel_id))


# ═══════════════════════════════════════════════════
# RESOURCES
# ═══════════════════════════════════════════════════

@views.route('/resources', methods=['GET', 'POST'])
@login_required
def resources():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        url_val = request.form.get('url', '').strip()
        resource_type = request.form.get('resource_type', 'link')
        description = request.form.get('description', '').strip()
        event_id = request.form.get('event_id', type=int)
        task_id = request.form.get('task_id', type=int)

        if title and url_val:
            res = Resource(
                user_id=get_current_user().id,
                title=title,
                url=url_val,
                resource_type=resource_type,
                description=description,
                event_id=event_id if event_id else None,
                task_id=task_id if task_id else None
            )
            db.session.add(res)
            db.session.flush()
            
            # Auto-post to #resources
            res_channel = Channel.query.filter(Channel.name.ilike('resources')).first()
            if not res_channel:
                res_channel = Channel(name='resources', description='Shared resources and links', channel_type='group', created_by=get_current_user().id)
                db.session.add(res_channel)
                db.session.flush()
                db.session.add(ChannelMember(channel_id=res_channel.id, user_id=get_current_user().id))
            
            # Ensure everyone is in #resources
            all_users = User.query.filter(User.id != get_current_user().id).all()
            for u in all_users:
                if not ChannelMember.query.filter_by(channel_id=res_channel.id, user_id=u.id).first():
                    db.session.add(ChannelMember(channel_id=res_channel.id, user_id=u.id))
            
            # Create Message with Metadata for Card
            # We keep the text for notifications, but add hidden data for the UI card
            import json
            card_data = {
                "type": "resource",
                "id": res.id,
                "title": res.title,
                "url": res.url,
                "resource_type": res.resource_type,
                "description": res.description or ""
            }
            msg_content = f"📊 **New Resource:** [{res.title}]({res.url})\n> {res.description or 'No description'} <!-- DATA: {json.dumps(card_data)} -->"
            
            sys_msg = Message(
                channel_id=res_channel.id,
                user_id=get_current_user().id,
                content=msg_content,
                message_type='text',
                is_system_message=True
            )
            db.session.add(sys_msg)
            db.session.commit()
            
            # Notify
            for u in all_users:
                 db.session.add(Notification(user_id=u.id, message_id=sys_msg.id))
            db.session.commit()

            flash(f'Resource "{title}" shared and posted to #resources!', 'success')
        return redirect(url_for('views.resources'))

    type_filter = request.args.get('type', '')
    event_filter = request.args.get('event', type=int)
    query = Resource.query

    if type_filter:
        query = query.filter_by(resource_type=type_filter)
    if event_filter:
        query = query.filter_by(event_id=event_filter)

    all_resources = query.order_by(Resource.created_at.desc()).all()
    all_events = Event.query.order_by(Event.event_date.desc()).all()
    return render_template('resources.html', resources=all_resources, type_filter=type_filter, event_filter=event_filter, all_events=all_events)


@views.route('/resources/<int:res_id>/delete', methods=['POST'])
@login_required
def delete_resource(res_id):
    res = Resource.query.get_or_404(res_id)
    user = get_current_user()
    if res.user_id != user.id and not user.can_manage_members():
        flash('Permission denied.', 'error')
        return redirect(url_for('views.resources'))
    db.session.delete(res)
    db.session.commit()
    flash('Resource deleted.', 'success')
    return redirect(url_for('views.resources'))


# ═══════════════════════════════════════════════════
# TASKS
# ═══════════════════════════════════════════════════

@views.route('/tasks')
@role_required('member')
def tasks():
    # Fetch members for the "Create Task" modal (assignees dropdown)
    members = User.query.filter(User.role != 'member').order_by(User.name).all() 
    return render_template('tasks.html', members=members, today=date.today())


@views.route('/tasks/assign', methods=['POST'])
@role_required('coordinator')
def assign_task():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    assigned_to_ids = request.form.getlist('assigned_to')
    due_date_str = request.form.get('due_date', '')
    is_open = request.form.get('is_open') == 'on'
    max_participants_str = request.form.get('max_participants', '').strip()
    priority = request.form.get('priority', 'medium')
    tags = request.form.get('tags', '').strip()

    max_participants = int(max_participants_str) if is_open and max_participants_str else None
    due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None

    task = Task(
        title=title,
        description=description,
        is_open=is_open,
        max_participants=max_participants,
        due_date=due_date,
        created_by=get_current_user().id,
        priority=priority,
        tags=tags
    )
    db.session.add(task)
    db.session.flush()

    for uid_str in assigned_to_ids:
        ta = TaskAssignee(task_id=task.id, user_id=int(uid_str))
        db.session.add(ta)

    db.session.commit()
    flash(f'Task "{title}" created!', 'success')
    return redirect(url_for('views.tasks'))


@views.route('/tasks/<int:task_id>/claim', methods=['POST'])
@login_required
def claim_task(task_id):
    task = Task.query.get_or_404(task_id)
    user = get_current_user()

    if not task.is_open:
        flash('Task not open.', 'error'); return redirect(url_for('views.tasks'))
    
    if task.max_participants and len(task.assignees) >= task.max_participants:
        flash('Task is full.', 'error'); return redirect(url_for('views.tasks'))

    existing = TaskAssignee.query.filter_by(task_id=task_id, user_id=user.id).first()
    if existing:
        flash('Already claimed.', 'warning'); return redirect(url_for('views.tasks'))

    db.session.add(TaskAssignee(task_id=task_id, user_id=user.id))
    if task.status == 'pending': task.status = 'in-progress'
    db.session.commit()
    flash(f'Claimed "{task.title}"!', 'success')
    return redirect(url_for('views.tasks'))


@views.route('/tasks/<int:task_id>/unclaim', methods=['POST'])
@login_required
def unclaim_task(task_id):
    task = Task.query.get_or_404(task_id)
    user = get_current_user()
    ta = TaskAssignee.query.filter_by(task_id=task_id, user_id=user.id).first()
    if ta:
        db.session.delete(ta)
        if TaskAssignee.query.filter_by(task_id=task_id).count() <= 1:
            task.status = 'pending'
        db.session.commit()
        flash(f'Unclaimed "{task.title}".', 'info')
    return redirect(url_for('views.tasks'))


@views.route('/tasks/<int:task_id>/submit_review', methods=['POST'])
@login_required
def submit_review(task_id):
    task = Task.query.get_or_404(task_id)
    task.status = 'review'
    db.session.commit()
    flash(f'"{task.title}" submitted.', 'success')
    return redirect(url_for('views.tasks'))


@views.route('/tasks/<int:task_id>/update', methods=['POST'])
@login_required
def update_task(task_id):
    task = Task.query.get_or_404(task_id)
    task.status = request.form.get('status', task.status)
    db.session.commit()
    flash(f'Status updated to {task.status}.', 'success')
    return redirect(url_for('views.tasks'))


@views.route('/tasks/<int:task_id>/delete', methods=['POST'])
@role_required('coordinator')
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    flash('Task deleted.', 'success')
    return redirect(url_for('views.tasks'))


# ═══════════════════════════════════════════════════
# CALENDAR
# ═══════════════════════════════════════════════════

@views.route('/calendar')
@login_required
def calendar_view():
    user = get_current_user()
    today = date.today()
    y = request.args.get('year', today.year, type=int)
    m = request.args.get('month', today.month, type=int)
    view_user_id = request.args.get('user_id', type=int)

    if m < 1: m, y = 12, y - 1
    elif m > 12: m, y = 1, y + 1

    month_cal = cal.monthcalendar(y, m)
    month_name = cal.month_name[m]

    events = Event.query.filter(db.extract('year', Event.event_date) == y, db.extract('month', Event.event_date) == m).order_by(Event.event_date).all()
    event_map = {}
    for e in events: event_map.setdefault(e.event_date.day, []).append(e)

    uid = view_user_id if view_user_id else user.id
    view_user = User.query.get_or_404(uid)
    task_ids = [ta.task_id for ta in TaskAssignee.query.filter_by(user_id=uid).all()]
    tasks_with_due = Task.query.filter(Task.id.in_(task_ids), Task.due_date.isnot(None), db.extract('year', Task.due_date) == y, db.extract('month', Task.due_date) == m).all()
    
    task_map = {}
    for t in tasks_with_due: task_map.setdefault(t.due_date.day, []).append(t)

    upcoming = Event.query.filter(Event.event_date >= today).order_by(Event.event_date).limit(5).all()
    all_members = User.query.order_by(User.name).all()

    return render_template('calendar.html', month_cal=month_cal, month_name=month_name, year=y, month=m, today=today, event_map=event_map, task_map=task_map, upcoming=upcoming, view_user=view_user, all_members=all_members)


@views.route('/calendar/add', methods=['POST'])
@role_required('coordinator')
def add_event():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    try:
        event_date = datetime.strptime(request.form.get('event_date'), '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format', 'error')
        return redirect(url_for('views.calendar_view'))

    event_type = request.form.get('event_type', 'event')
    
    event = Event(
        title=title, 
        description=description, 
        event_date=event_date, 
        event_time=request.form.get('event_time'), 
        location=request.form.get('location'), 
        created_by=get_current_user().id,
        event_type=event_type
    )
    db.session.add(event)
    db.session.commit()
    
    # Create Notification for all users
    # 1. Find or create #meetings channel
    meetings_channel = Channel.query.filter(Channel.name.ilike('meetings')).first()
    if not meetings_channel:
        meetings_channel = Channel(name='meetings', description='Meeting minutes and schedules', channel_type='group', created_by=get_current_user().id)
        db.session.add(meetings_channel)
        db.session.flush()
        # Add creator
        db.session.add(ChannelMember(channel_id=meetings_channel.id, user_id=get_current_user().id))
    
    # 2. Create a system message with @all mention and Metadata
    import json
    icon = '🤝' if event_type == 'meeting' else '📅'
    card_data = {
        "type": event_type, # 'event' or 'meeting'
        "id": event.id,
        "title": event.title,
        "date": event.event_date.strftime('%b %d, %Y'),
        "time": event.event_time or "",
        "location": event.location or "",
        "description": event.description or ""
    }
    
    msg_content = f"@all {icon} **New {event_type.capitalize()}:** {title} on {event_date.strftime('%b %d')} <!-- DATA: {json.dumps(card_data)} -->"
    
    sys_msg = Message(
        channel_id=meetings_channel.id,
        user_id=get_current_user().id, # Sent by the creator
        content=msg_content,
        message_type='text', 
        is_system_message=True
    )
    db.session.add(sys_msg)
    db.session.flush() # Get ID
    
    # 3. Create notifications for all OTHER users
    all_users = User.query.filter(User.id != get_current_user().id).all()
    for u in all_users:
        # Auto-add to meetings channel if not present
        if not ChannelMember.query.filter_by(channel_id=meetings_channel.id, user_id=u.id).first():
             db.session.add(ChannelMember(channel_id=meetings_channel.id, user_id=u.id))
        
        n = Notification(user_id=u.id, message_id=sys_msg.id)
        db.session.add(n)
    
    db.session.commit()

    flash(f'{event_type.capitalize()} "{title}" added and posted to #meetings!', 'success')
    return redirect(url_for('views.event_details', event_id=event.id))


@views.route('/calendar/<int:event_id>/delete', methods=['POST'])
@role_required('coordinator')
def delete_event(event_id):
    db.session.delete(Event.query.get_or_404(event_id))
    db.session.commit()
    flash('Event deleted.', 'success')
    return redirect(url_for('views.calendar_view'))


@views.route('/events/<int:event_id>', methods=['GET', 'POST'])
@login_required
def event_details(event_id):
    event = Event.query.get_or_404(event_id)
    user = get_current_user()

    if request.method == 'POST':
        if not user.can_manage_calendar():
            flash('Permission denied.', 'error')
            return redirect(url_for('views.event_details', event_id=event.id))

        # Handle MoM Update
        if 'mom' in request.form:
            new_mom = request.form.get('mom')
            if new_mom and new_mom != event.mom:
                event.mom = new_mom
                db.session.commit()
                flash('Minutes of Meeting updated.', 'success')

                # Post to #meetings channel
                meetings_channel = Channel.query.filter(Channel.name.ilike('meetings')).first()
                if not meetings_channel:
                    # Create if doesn't exist
                    meetings_channel = Channel(
                        name='meetings', 
                        description='Official Minutes of Meetings', 
                        channel_type='group',
                        is_private=False,
                        created_by=user.id
                    )
                    db.session.add(meetings_channel)
                    db.session.flush()
                    # Add creator as member
                    db.session.add(ChannelMember(channel_id=meetings_channel.id, user_id=user.id))
                
                # Ensure user handles membership if private (but we made it public)
                # Post message with Metadata
                import json
                card_data = {
                    "type": "mom",
                    "id": event.id,
                    "title": event.title,
                    "date": event.event_date.strftime('%b %d'),
                    "mom_full": new_mom  # Send full content
                }
                mom_msg_content = f"📝 **MoM Posted:** {event.title}\n\n{new_mom[:100]}... <!-- DATA: {json.dumps(card_data)} -->"
                
                mom_msg = Message(
                    channel_id=meetings_channel.id,
                    user_id=user.id,
                    content=mom_msg_content,
                    message_type='text',
                    is_system_message=True
                )
                db.session.add(mom_msg)
                db.session.commit()
                flash('MoM posted to #meetings channel.', 'info')
        
        # Handle Attendance Update
        elif 'attendance_submitted' in request.form:
            # Clear existing for this event (simple approach, or update/upsert)
            # For simplicity, we can iterate all users and check their status from form
            all_members = User.query.all()
            for member in all_members:
                status = request.form.get(f'status_{member.id}') # present, absent, excused, or None
                if status:
                    att = Attendance.query.filter_by(event_id=event.id, user_id=member.id).first()
                    if not att:
                        att = Attendance(event_id=event.id, user_id=member.id)
                        db.session.add(att)
                    att.status = status
            db.session.commit()
            flash('Attendance updated.', 'success')

        return redirect(url_for('views.event_details', event_id=event.id))

    # GET request
    all_members = User.query.order_by(User.name).all()
    # Create a map of user_id -> attendance_status
    attendance_map = {a.user_id: a.status for a in event.attendance_records}
    
    return render_template('event_details.html', event=event, all_members=all_members, attendance_map=attendance_map)


# ═══════════════════════════════════════════════════
# SHEETS
# ═══════════════════════════════════════════════════

@views.route('/sheets')
@login_required
def sheets():
    all_sheets = Sheet.query.order_by(Sheet.created_at.desc()).all()
    channels = Channel.query.filter_by(channel_type='group').all()
    return render_template('sheets.html', sheets=all_sheets, channels=channels)


@views.route('/sheets/create', methods=['POST'])
@login_required
def create_sheet():
    name = request.form.get('name', 'Untitled Sheet').strip()
    channel_id = request.form.get('channel_id', type=int)
    sheet = Sheet(name=name, created_by=get_current_user().id, channel_id=channel_id if channel_id else None)
    db.session.add(sheet)
    db.session.flush()
    
    # Auto-post to #resources
    res_channel = Channel.query.filter(Channel.name.ilike('resources')).first()
    if not res_channel:
        res_channel = Channel(name='resources', description='Shared resources and links', channel_type='group', created_by=get_current_user().id)
        db.session.add(res_channel)
        db.session.flush()
        db.session.add(ChannelMember(channel_id=res_channel.id, user_id=get_current_user().id))

    # Ensure everyone is in #resources
    all_users = User.query.filter(User.id != get_current_user().id).all()
    for u in all_users:
        if not ChannelMember.query.filter_by(channel_id=res_channel.id, user_id=u.id).first():
            db.session.add(ChannelMember(channel_id=res_channel.id, user_id=u.id))

    # Create Message
    # We need a link to the sheet. url_for requires an ID, which we have after flush/commit logic? 
    # Logic above did flush, so sheet.id is available.
    sheet_link = url_for('views.sheet_view', sheet_id=sheet.id, _external=True) 
    
    import json
    card_data = {
        "type": "resource", # Treat sheet as a resource card
        "resource_type": "sheet", # custom subtype
        "id": sheet.id,
        "title": name,
        "url": sheet_link,
        "description": "Shared Spreadsheet"
    }
    
    msg_content = f"📗 **New Sheet:** [{name}]({sheet_link}) <!-- DATA: {json.dumps(card_data)} -->"
    
    sys_msg = Message(
        channel_id=res_channel.id,
        user_id=get_current_user().id,
        content=msg_content,
        message_type='text',
        is_system_message=True
    )
    db.session.add(sys_msg)
    db.session.commit()

    # Notify
    for u in all_users:
            db.session.add(Notification(user_id=u.id, message_id=sys_msg.id))
    db.session.commit()

    flash(f'Sheet "{name}" created and posted to #resources!', 'success')
    return redirect(url_for('views.sheet_view', sheet_id=sheet.id))


@views.route('/sheets/<int:sheet_id>')
@login_required
def sheet_view(sheet_id):
    sheet = Sheet.query.get_or_404(sheet_id)
    return render_template('sheet_editor.html', sheet=sheet)


@views.route('/api/tour/complete', methods=['POST'])
@login_required
def complete_tour():
    user = get_current_user()
    user.has_seen_tour = True
    db.session.commit()
    return jsonify({'success': True})


@views.route('/sheets/<int:sheet_id>/delete', methods=['POST'])
@login_required
def delete_sheet(sheet_id):
    sheet = Sheet.query.get_or_404(sheet_id)
    if sheet.created_by != get_current_user().id and get_current_user().role != 'jsec': abort(403)
    db.session.delete(sheet)
    db.session.commit()
    flash('Sheet deleted.', 'info')
    return redirect(url_for('views.sheets'))
