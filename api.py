from flask import Blueprint, request, jsonify
from datetime import datetime
from models import db, User, Message, Resource, Task, TaskAssignee, Channel, ChannelMember, Poll, PollOption, PollVote, MessageReaction, SheetCell, Notification, TaskAuditLog, Achievement
from helpers import login_required, get_current_user, role_required
import re

api = Blueprint('api', __name__)

@api.route('/channels')
@login_required
def get_channels():
    """Get list of channels visible to current user."""
    user = get_current_user()
    
    # Logic:
    # 1. Groups: Show ALL that are NOT private.
    # 2. Groups (Private): Show only if member.
    # 3. DMs: Show only if member.
    
    # User is member of:
    my_channel_ids = [cm.channel_id for cm in ChannelMember.query.filter_by(user_id=user.id).all()]
    
    # Query: (is_private=False AND channel_type='group') OR (id IN my_channel_ids)
    channels = Channel.query.filter(
        db.or_(
            db.and_(Channel.is_private == False, Channel.channel_type == 'group'),
            Channel.id.in_(my_channel_ids)
        )
    ).distinct().order_by(Channel.created_at).all()
        
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'channel_type': c.channel_type,
        'is_private': c.is_private,
        'is_member': c.id in my_channel_ids,
        'other_user_name': User.query.get(ChannelMember.query.filter(ChannelMember.channel_id==c.id, ChannelMember.user_id!=user.id).first().user_id).name if c.channel_type == 'dm' and ChannelMember.query.filter(ChannelMember.channel_id==c.id, ChannelMember.user_id!=user.id).first() else None,
        'other_user_avatar_color': User.query.get(ChannelMember.query.filter(ChannelMember.channel_id==c.id, ChannelMember.user_id!=user.id).first().user_id).avatar_color if c.channel_type == 'dm' and ChannelMember.query.filter(ChannelMember.channel_id==c.id, ChannelMember.user_id!=user.id).first() else None
    } for c in channels])


@api.route('/messages/<int:channel_id>')
@login_required
def api_messages(channel_id):
    user = get_current_user()
    is_member = ChannelMember.query.filter_by(channel_id=channel_id, user_id=user.id).first()
    if not is_member: return jsonify([]), 403

    after_id = request.args.get('after', 0, type=int)
    before_id = request.args.get('before', 0, type=int)
    limit = request.args.get('limit', 100, type=int)
    
    query = Message.query.filter_by(channel_id=channel_id)
    
    if before_id:
        # Load older messages (Pagination)
        query = query.filter(Message.id < before_id).order_by(Message.id.desc()).limit(limit)
        messages = list(reversed(query.all()))
    elif after_id:
        # Load newer messages (Polling)
        query = query.filter(Message.id > after_id).order_by(Message.id.asc()).limit(limit)
        messages = query.all()
    else:
        # Initial load: Latest N messages
        query = query.order_by(Message.id.desc()).limit(limit)
        messages = list(reversed(query.all()))

    result = []
    for msg in messages:
        reactions_raw = MessageReaction.query.filter_by(message_id=msg.id).all()
        reactions_map = {}
        for r in reactions_raw:
            if r.emoji not in reactions_map: reactions_map[r.emoji] = {'count': 0, 'users': [], 'user_reacted': False}
            reactions_map[r.emoji]['count'] += 1
            reactions_map[r.emoji]['users'].append(r.user_id)
            if r.user_id == user.id: reactions_map[r.emoji]['user_reacted'] = True

        poll_data = None
        poll = Poll.query.filter_by(message_id=msg.id).first()
        if poll:
            total_votes = sum(len(opt.votes) for opt in poll.options)
            poll_data = {
                'id': poll.id,
                'question': poll.question,
                'is_active': poll.is_active,
                'options': [{
                    'id': opt.id,
                    'text': opt.text,
                    'votes': len(opt.votes),
                    'pct': round(len(opt.votes) / total_votes * 100) if total_votes else 0,
                    'user_voted': any(v.user_id == user.id for v in opt.votes),
                    'voters': [{'id': v.user.id, 'name': v.user.name} for v in opt.votes]
                } for opt in poll.options],
                'total_votes': total_votes
            }

        result.append({
            'id': msg.id,
            'user_id': msg.user_id,
            'content': msg.content,
            'message_type': msg.message_type,
            'author_name': msg.author.name,
            'author_role': msg.author.role,
            'author_avatar_color': msg.author.avatar_color,
            'created_at': msg.created_at.strftime('%I:%M %p'),
            'is_own': msg.user_id == user.id,
            'referenced_task': {'title': msg.referenced_task.title, 'status': msg.referenced_task.status, 'due_date': msg.referenced_task.due_date.strftime('%b %d') if msg.referenced_task.due_date else None} if msg.referenced_task else None,
            'reactions': reactions_map,
            'poll': poll_data
        })
    return jsonify(result)


@api.route('/messages/<int:channel_id>/send', methods=['POST'])
@login_required
def api_send_message(channel_id):
    user = get_current_user()
    if not ChannelMember.query.filter_by(channel_id=channel_id, user_id=user.id).first():
        return jsonify({'error': 'Not a member'}), 403

    data = request.get_json() or {}
    content = data.get('content', '').strip()
    
    if not content: return jsonify({'error': 'Empty'}), 400

    msg = Message(
        user_id=user.id, content=content, channel_id=channel_id,
        message_type=data.get('message_type', 'text'),
        referenced_task_id=data.get('referenced_task_id')
    )
    db.session.add(msg)
    db.session.commit()
    
    # Mentions (for group channels)
    mentioned_tokens = set(re.findall(r"@([a-zA-Z0-9_ -]+)", content))
    notify_user_ids = set()
    
    if mentioned_tokens:
        # 1. Handle Role Mentions
        roles_map = {
            'jsec': 'jsec',
            'coordinator': 'coordinator', 
            'member': 'member'
        }
        
        # Helper to find users by role
        def get_users_by_role(r_name):
            if r_name == 'all':
                # Notify all members of this channel
                 members = ChannelMember.query.filter_by(channel_id=channel_id).all()
                 return [m.user_id for m in members]
            return [u.id for u in User.query.filter_by(role=roles_map[r_name]).all()]

        for token in mentioned_tokens:
            token_clean = token.strip()
            token_lower = token_clean.lower()
            
            # Check if it STARTS with a role (to handle greedy regex matching like "all hello")
            found_role = None
            if token_lower == 'all' or token_lower.startswith('all '):
                found_role = 'all'
            else:
                for r in roles_map:
                    if token_lower == r or token_lower.startswith(r + ' '):
                        found_role = r
                        break
            
            if found_role:
                notify_user_ids.update(get_users_by_role(found_role))
                # Note: We assume if it matched a role, it's not a username mention (or priority given to role)
            else:
                # 2. Handle Name Mentions
                # Exact match check
                u = User.query.filter(User.name == token_clean).first()
                if u: 
                    notify_user_ids.update([u.id])
        
        # 3. Create Notifications
        if user.id in notify_user_ids: notify_user_ids.remove(user.id)
        
        for uid in notify_user_ids:
            # Check for existing to avoid duplicates if multiple mentions target same user
             if not Notification.query.filter_by(user_id=uid, message_id=msg.id).first():
                db.session.add(Notification(user_id=uid, message_id=msg.id))
        
        db.session.commit()

    # DM auto-notification: notify other user without needing @mention
    channel = Channel.query.get(channel_id)
    if channel and channel.channel_type == 'dm':
        dm_members = ChannelMember.query.filter_by(channel_id=channel_id).all()
        for m in dm_members:
            if m.user_id != user.id:
                # Only create if not already notified via @mention above or role
                existing = Notification.query.filter_by(user_id=m.user_id, message_id=msg.id).first()
                if not existing:
                    db.session.add(Notification(user_id=m.user_id, message_id=msg.id))
        db.session.commit()

    return jsonify({'id': msg.id, 'content': msg.content, 'created_at': msg.created_at.strftime('%I:%M %p')})


@api.route('/messages/<int:msg_id>/react', methods=['POST'])
@login_required
def api_react(msg_id):
    user = get_current_user()
    emoji = (request.get_json() or {}).get('emoji')
    if not emoji: return jsonify({'error': 'No emoji'}), 400

    existing = MessageReaction.query.filter_by(message_id=msg_id, user_id=user.id, emoji=emoji).first()
    if existing:
        db.session.delete(existing)
        action = 'removed'
    else:
        db.session.add(MessageReaction(message_id=msg_id, user_id=user.id, emoji=emoji))
        action = 'added'
    db.session.commit()
    return jsonify({'action': action})


@api.route('/messages/<int:msg_id>/delete', methods=['POST'])
@login_required
def api_delete_message(msg_id):
    msg = Message.query.get_or_404(msg_id)
    user = get_current_user()
    if msg.user_id != user.id and user.role != 'jsec': return jsonify({'error': 'Permission denied'}), 403
    
    # Clean up Polls
    poll = Poll.query.filter_by(message_id=msg.id).first()
    if poll:
        for opt in poll.options: PollVote.query.filter_by(option_id=opt.id).delete()
        PollOption.query.filter_by(poll_id=poll.id).delete()
        db.session.delete(poll)
    
    MessageReaction.query.filter_by(message_id=msg.id).delete()
    db.session.delete(msg)
    db.session.commit()
    return jsonify({'deleted': True})


@api.route('/polls/create', methods=['POST'])
@login_required
def api_create_poll():
    user = get_current_user()
    data = request.get_json() or {}
    channel_id = data.get('channel_id')
    question = data.get('question')
    options = data.get('options', [])
    
    if not ChannelMember.query.filter_by(channel_id=channel_id, user_id=user.id).first():
        return jsonify({'error': 'Not a member'}), 403
        
    msg = Message(user_id=user.id, content=f'📊 Poll: {question}', channel_id=channel_id, message_type='poll')
    db.session.add(msg)
    db.session.flush()
    
    poll = Poll(channel_id=channel_id, message_id=msg.id, created_by=user.id, question=question)
    db.session.add(poll)
    db.session.flush()
    
    for i, txt in enumerate(options):
        db.session.add(PollOption(poll_id=poll.id, text=txt.strip(), sort_order=i))
        
    db.session.commit()
    return jsonify({'poll_id': poll.id})


@api.route('/polls/<int:poll_id>/vote', methods=['POST'])
@login_required
def api_vote_poll(poll_id):
    user = get_current_user()
    opt_id = (request.get_json() or {}).get('option_id')
    poll = Poll.query.get_or_404(poll_id)
    
    if not poll.is_active: return jsonify({'error': 'Closed'}), 400
    
    # Remove old vote
    for opt in poll.options:
        existing = PollVote.query.filter_by(option_id=opt.id, user_id=user.id).first()
        if existing: db.session.delete(existing)
        
    db.session.add(PollVote(option_id=opt_id, user_id=user.id))
    db.session.commit()
    return jsonify({'voted': True})


@api.route('/members')
@login_required
def api_members():
    members = User.query.order_by(User.name).all()
    return jsonify([{'id': m.id, 'name': m.name, 'unique_id': m.unique_id, 'role': m.role, 'avatar_color': m.avatar_color} for m in members])


@api.route('/resources')
@login_required
def api_resources():
    resources = Resource.query.order_by(Resource.title).all()
    return jsonify([{'id': r.id, 'title': r.title, 'resource_type': r.resource_type, 'link': r.url} for r in resources])


@api.route('/sheets/<int:sheet_id>/data')
@login_required
def api_sheet_data(sheet_id):
    cells = SheetCell.query.filter_by(sheet_id=sheet_id).all()
    data = {}
    for c in cells:
        if c.row not in data: data[c.row] = {}
        data[c.row][c.col] = c.content
    return jsonify(data)


@api.route('/sheets/<int:sheet_id>/update', methods=['POST'])
@login_required
def api_update_sheet(sheet_id):
    data = request.get_json() or {}
    row, col, content = data.get('row'), data.get('col'), data.get('content', '')
    cell = SheetCell.query.filter_by(sheet_id=sheet_id, row=row, col=col).first()
    if cell: cell.content = content
    else: db.session.add(SheetCell(sheet_id=sheet_id, row=row, col=col, content=content))
    db.session.commit()
    return jsonify({'success': True})


@api.route('/sheets/<int:sheet_id>/bulk_update', methods=['POST'])
@login_required
def api_bulk_update_sheet(sheet_id):
    cells = (request.get_json() or {}).get('cells', [])
    for item in cells:
        row, col, content = item.get('row'), item.get('col'), item.get('content', '')
        cell = SheetCell.query.filter_by(sheet_id=sheet_id, row=row, col=col).first()
        if cell: cell.content = content
        else: db.session.add(SheetCell(sheet_id=sheet_id, row=row, col=col, content=content))
    db.session.commit()
    return jsonify({'success': True})


@api.route('/notifications')
@login_required
def get_notifications():
    user = get_current_user()
    notifs = Notification.query.filter_by(user_id=user.id, is_read=False).order_by(Notification.created_at.desc()).all()
    return jsonify([{
        'id': n.id, 'message_id': n.message_id, 'channel_id': n.message.channel_id,
        'author_name': n.message.author.name, 'content': n.message.content,
        'created_at': n.created_at.strftime('%I:%M %p')
    } for n in notifs])


@api.route('/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    if notif.user_id != get_current_user().id: abort(403)
    notif.is_read = True
    db.session.commit()
    return jsonify({'success': True})


@api.route('/channels/<int:channel_id>/mute', methods=['POST'])
@login_required
def toggle_mute(channel_id):
    cm = ChannelMember.query.filter_by(channel_id=channel_id, user_id=get_current_user().id).first()
    if not cm: return jsonify({'error': 'Not a member'}), 403
    cm.is_muted = not cm.is_muted
    db.session.commit()
    return jsonify({'is_muted': cm.is_muted})

@api.route('/channels/<int:channel_id>/pin', methods=['POST'])
@login_required
def toggle_pin(channel_id):
    cm = ChannelMember.query.filter_by(channel_id=channel_id, user_id=get_current_user().id).first()
    if not cm: return jsonify({'error': 'Not a member'}), 403
    cm.is_pinned = not cm.is_pinned
    db.session.commit()
    return jsonify({'is_pinned': cm.is_pinned})

@api.route('/channels/<int:channel_id>/archive', methods=['POST'])
@login_required
def toggle_archive(channel_id):
    cm = ChannelMember.query.filter_by(channel_id=channel_id, user_id=get_current_user().id).first()
    if not cm: return jsonify({'error': 'Not a member'}), 403
    cm.is_archived = not cm.is_archived
    db.session.commit()
    return jsonify({'is_archived': cm.is_archived})


# ─── Tasks API ───
@api.route('/tasks')
@login_required
def get_tasks_api():
    tasks = Task.query.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc()).all()
    user = get_current_user()
    return jsonify([{
        'id': t.id,
        'title': t.title,
        'description': t.description,
        'status': t.status,
        'priority': t.priority,
        'is_open': t.is_open,
        'max_participants': t.max_participants,
        'due_date': t.due_date.strftime('%Y-%m-%d') if t.due_date else None,
        'short_date': t.due_date.strftime('%b %d') if t.due_date else None,
        'tags': t.tags.split(',') if t.tags else [],
        'assignees': [{'id': u.id, 'name': u.name, 'avatar_color': u.avatar_color} for u in t.assignee_list()],
        'is_assigned_to_me': user.id in [u.id for u in t.assignee_list()],
        'is_creator': t.created_by == user.id,
        'resources_count': len(t.resources)
    } for t in tasks])

@api.route('/tasks/<int:task_id>')
@login_required
def get_task_detail(task_id):
    t = Task.query.get_or_404(task_id)
    user = get_current_user()
    assignee_list = t.assignee_list()
    return jsonify({
        'id': t.id,
        'title': t.title,
        'description': t.description,
        'status': t.status,
        'priority': t.priority,
        'due_date': t.due_date.strftime('%Y-%m-%d') if t.due_date else None,
        'tags': t.tags,
        'is_open': t.is_open,
        'max_participants': t.max_participants,
        'assignee_ids': [{'id': u.id, 'name': u.name} for u in assignee_list if u],
        'is_assigned_to_me': user.id in [u.id for u in assignee_list if u],
        'submission_link': t.submission_link or '',
        'submission_notes': t.submission_notes or '',
        'resources': [{'id': r.id, 'title': r.title, 'link': r.url, 'type': r.resource_type} for r in t.resources],
        'audit_logs': [{'user': l.user.name, 'action': l.action, 'details': l.details, 'time': l.created_at.strftime('%Y-%m-%d %H:%M')} for l in t.logs]
    })

@api.route('/tasks/create', methods=['POST'])
@login_required
def create_task_api():
    user = get_current_user()
    if not user.can_assign_work(): return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json() or {}
    print(data)
    task = Task(
        title=data.get('title'),
        description=data.get('description', ''),
        priority=data.get('priority', 'medium'),
        tags=data.get('tags', ''),
        is_open=data.get('is_open', False),
        max_participants=int(data.get('max_participants')) if data.get('max_participants') else None,
        created_by=user.id,
        status='pending'
    )
    
    if data.get('due_date'):
        task.due_date = datetime.strptime(data.get('due_date'), '%Y-%m-%d').date()
        
    db.session.add(task)
    db.session.flush()
    
    # Assignees
    assignee_ids = data.get('assignee_ids', [])
    for uid in assignee_ids:
        db.session.add(TaskAssignee(task_id=task.id, user_id=uid))
        
    db.session.commit()
    return jsonify({'id': task.id})

@api.route('/tasks/<int:task_id>/update', methods=['POST'])
@login_required
def update_task_api(task_id):
    task = Task.query.get_or_404(task_id)
    user = get_current_user()

    can_manage = user.can_assign_work() or user.id == task.created_by
    is_assignee = user.id in task.assignee_users()

    if not (can_manage or is_assignee):
        return jsonify({'error': 'Permission denied'}), 403

    data = request.get_json() or {}
    changes = []

    # Status Transitions
    if 'status' in data:
        new_status = data['status']
        if new_status != task.status:
            if new_status == 'done':
                if not user.can_assign_work(): return jsonify({'error': 'Only Admins can approve tasks'}), 403
            elif new_status == 'review':
                if not is_assignee: return jsonify({'error': 'Only assignees can submit for review'}), 403
            elif task.status == 'done' and new_status == 'in-progress':
                 if not user.can_assign_work(): return jsonify({'error': 'Only Admins can re-open tasks'}), 403
            
            db.session.add(TaskAuditLog(task_id=task.id, user_id=user.id, action='status_change', details=f"Changed status from {task.status} to {new_status}"))
            task.status = new_status
            changes.append('status')

    # Other updates (Title, Desc, etc.) - Manager only
    if can_manage:
        if 'priority' in data: 
            task.priority = data['priority']
        if 'title' in data: 
            task.title = data['title']
        if 'description' in data: 
            task.description = data['description']
        if 'tags' in data: 
            task.tags = data['tags']
        if 'due_date' in data:
             task.due_date = datetime.strptime(data['due_date'], '%Y-%m-%d').date() if data['due_date'] else None
            
    # Submission Updates (Assignee can also do this)
    if is_assignee or can_manage:
        if 'submission_link' in data:
            task.submission_link = data['submission_link']
        if 'submission_notes' in data:
            task.submission_notes = data['submission_notes']
        
        # Handle assignees update (Manager only)
        if 'assignee_ids' in data and user.can_assign_work():
            old_ids = set(task.assignee_users())
            new_ids = set(data['assignee_ids'])
            
            added = new_ids - old_ids
            removed = old_ids - new_ids
            
            if added or removed:
                TaskAssignee.query.filter_by(task_id=task.id).delete()
                for uid in data['assignee_ids']:
                    db.session.add(TaskAssignee(task_id=task.id, user_id=uid))
                
                if added: db.session.add(TaskAuditLog(task_id=task.id, user_id=user.id, action='assigned', details=f"Assigned user IDs: {list(added)}"))
                if removed: db.session.add(TaskAuditLog(task_id=task.id, user_id=user.id, action='unassigned', details=f"Removed user IDs: {list(removed)}"))
                changes.append('assignees')

    db.session.commit()
    return jsonify({'success': True})


@api.route('/tasks/<int:task_id>/claim', methods=['POST'])
@login_required
def api_claim_task(task_id):
    task = Task.query.get_or_404(task_id)
    user = get_current_user()

    if not task.is_open:
        return jsonify({'error': 'Task is not open for claiming'}), 400
    
    if task.max_participants and len(task.assignees) >= task.max_participants:
        return jsonify({'error': 'Task is full'}), 400

    existing = TaskAssignee.query.filter_by(task_id=task_id, user_id=user.id).first()
    if existing:
        return jsonify({'error': 'Already claimed'}), 400

    db.session.add(TaskAssignee(task_id=task_id, user_id=user.id))
    
    # Auto-move to in-progress if pending
    if task.status == 'pending': 
        task.status = 'in-progress'
        db.session.add(TaskAuditLog(task_id=task.id, user_id=user.id, action='status_change', details="Auto-started upon claim"))

    db.session.add(TaskAuditLog(task_id=task.id, user_id=user.id, action='claimed', details="User claimed the task"))
    db.session.commit()
    return jsonify({'success': True})


@api.route('/tasks/<int:task_id>/unclaim', methods=['POST'])
@login_required
def api_unclaim_task(task_id):
    task = Task.query.get_or_404(task_id)
    user = get_current_user()
    
    # Check 24h deadline
    if task.due_date:
        delta = task.due_date - datetime.now().date()
        if delta.days < 1:
            return jsonify({'error': 'Cannot revert task within 24h of due date. Contact a Coordinator.'}), 400

    ta = TaskAssignee.query.filter_by(task_id=task_id, user_id=user.id).first()
    if ta:
        db.session.delete(ta)
        db.session.add(TaskAuditLog(task_id=task_id, user_id=user.id, action='reverted', details="User reverted the task"))
        
        # If no assignees left, move back to pending?
        if TaskAssignee.query.filter_by(task_id=task_id).count() <= 1: # <=1 because we just deleted one but not committed yet? No, session.delete marks it.
             # Actually count() might still see it if checking db, but let's assume standard behavior.
             # Safer:
             pass 
             
        db.session.commit()
        
        # Post-commit check to reset status
        if not task.assignees:
            task.status = 'pending'
            db.session.commit()
            
        return jsonify({'success': True})
    
    return jsonify({'error': 'Not assigned'}), 400

@api.route('/tasks/<int:task_id>/attach', methods=['POST'])
@login_required
def attach_resource_to_task(task_id):
    task = Task.query.get_or_404(task_id)
    data = request.get_json() or {}
    
    res = Resource(
        user_id=get_current_user().id,
        title=data.get('title', 'Attachment'),
        url=data.get('url'),
        resource_type='link',
        task_id=task.id
    )
    db.session.add(res)
    db.session.commit()
    return jsonify({'success': True})

@api.route('/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task_api(task_id):
     task = Task.query.get_or_404(task_id)
     if not get_current_user().can_assign_work(): return jsonify({'error': 'Permission denied'}), 403
     
     db.session.delete(task)
     db.session.commit()
     return jsonify({'success': True})


# ═══════════════════════════════════════════════════
# ACHIEVEMENTS
# ═══════════════════════════════════════════════════

@api.route('/achievements/<int:user_id>', methods=['GET'])
@login_required
def get_achievements(user_id):
    achievements = Achievement.query.filter_by(user_id=user_id).order_by(Achievement.created_at.desc()).all()
    return jsonify([{
        'id': a.id, 'title': a.title, 'description': a.description,
        'category': a.category, 'icon': a.icon, 'status': a.status,
        'awarded_by': a.awarder.name if a.awarder else '',
        'approved_by': a.approver.name if a.approver else '',
        'created_at': a.created_at.strftime('%b %d, %Y')
    } for a in achievements])


@api.route('/achievements/<int:user_id>/add', methods=['POST'])
@login_required
def add_achievement(user_id):
    user = get_current_user()
    if not user.can_assign_work():
        return jsonify({'error': 'Only JSECs and Coordinators can add achievements'}), 403
    
    target = User.query.get_or_404(user_id)
    data = request.get_json() or {}
    
    if not data.get('title'):
        return jsonify({'error': 'Title is required'}), 400
    
    achievement = Achievement(
        user_id=target.id,
        title=data['title'],
        description=data.get('description', ''),
        category=data.get('category', 'general'),
        icon=data.get('icon', '🏆'),
        awarded_by=user.id,
        status='approved' if user.role == 'jsec' else 'pending'
    )
    
    if user.role == 'jsec':
        achievement.approved_by = user.id
        achievement.approved_at = datetime.utcnow()
    
    db.session.add(achievement)
    db.session.commit()
    return jsonify({'success': True, 'id': achievement.id})


@api.route('/achievements/<int:achievement_id>/review', methods=['POST'])
@login_required
def review_achievement(achievement_id):
    user = get_current_user()
    if user.role != 'jsec':
        return jsonify({'error': 'Only JSECs can review achievements'}), 403
    
    achievement = Achievement.query.get_or_404(achievement_id)
    data = request.get_json() or {}
    action = data.get('action')  # 'approve' or 'reject'
    
    if action == 'approve':
        achievement.status = 'approved'
        achievement.approved_by = user.id
        achievement.approved_at = datetime.utcnow()
    elif action == 'reject':
        achievement.status = 'rejected'
    else:
        return jsonify({'error': 'Invalid action'}), 400
    
    db.session.commit()
    return jsonify({'success': True})


# ═══════════════════════════════════════════════════
# PROFILE UPDATE (self-service)
# ═══════════════════════════════════════════════════

@api.route('/profile/update', methods=['POST'])
@login_required
def update_profile_api():
    user = get_current_user()
    data = request.get_json() or {}
    
    if 'bio' in data:
        user.bio = data['bio'][:500]
    if 'expertise' in data:
        user.expertise = data['expertise'][:255]
    if 'current_work' in data:
        user.current_work = data['current_work'][:255]
    
    db.session.commit()
    return jsonify({'success': True})
