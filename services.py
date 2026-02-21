from models import db, User, Task, TaskAuditLog, TaskAssignee, Event, Attendance
from datetime import datetime, timedelta, date
from sqlalchemy import func, desc

class AnalyticsService:
    @staticmethod
    def get_productivity_stats():
        """
        Calculate productivity metrics:
        - Completion Rate (global)
        - Average time to completion (TODO)
        - Bottleneck: Tasks stuck in review
        """
        total_tasks = Task.query.count()
        completed_tasks = Task.query.filter_by(status='done').count()
        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        # Bottleneck: Tasks in review
        tasks_in_review = Task.query.filter_by(status='review').count()
        
        return {
            'completion_rate': round(completion_rate, 1),
            'tasks_in_review': tasks_in_review,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks
        }

    @staticmethod
    def get_engagement_stats():
        """
        Identify silent members and top contributors.
        Silent: No login in 30 days OR no task activity in 30 days.
        """
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        # Silent Members (inactive login)
        silent_members = User.query.filter(User.last_seen < thirty_days_ago).all()
        
        # Top Contributors (most tasks completed)
        # This is a bit complex with current schema, requires joining TaskAssignee and Task
        top_contributors = db.session.query(
            User, func.count(TaskAssignee.task_id).label('task_count')
        ).join(TaskAssignee).join(Task).filter(
            Task.status == 'done'
        ).group_by(User.id).order_by(desc('task_count')).limit(5).all()
        
        # Format for template
        leaderboard = [{'name': u.name, 'count': c, 'avatar_color': u.avatar_color} for u, c in top_contributors]
        
        return {
            'silent_members_count': len(silent_members),
            'silent_members': silent_members, # List of User objects
            'leaderboard': leaderboard
        }

    @staticmethod
    def get_workload_heatmap():
        """
        Return list of users with their active task count to visualize burnout risk.
        """
        # counts active tasks (not done)
        active_counts = db.session.query(
            User, func.count(TaskAssignee.task_id).label('active_count')
        ).join(TaskAssignee).join(Task).filter(
            Task.status.in_(['pending', 'in-progress', 'review'])
        ).group_by(User.id).order_by(desc('active_count')).all()
        
        return [{'name': u.name, 'count': c, 'risk': 'High' if c > 3 else 'Normal'} for u, c in active_counts]

    @staticmethod
    def get_attendance_stats():
        """
        Return stats for recent (past) events (meetings).
        """
        # Get last 5 events that have passed
        recent_events = Event.query.filter(Event.event_date <= date.today()).order_by(Event.event_date.desc()).limit(5).all()
        
        event_stats = []
        for event in recent_events:
            total_records = len(event.attendance_records)
            present = sum(1 for a in event.attendance_records if a.status == 'present')
            absent = sum(1 for a in event.attendance_records if a.status == 'absent')
            excused = sum(1 for a in event.attendance_records if a.status == 'excused')
            
            # If no records, assume 0% or N/A
            rate = (present / total_records * 100) if total_records > 0 else 0
            
            event_stats.append({
                'title': event.title,
                'date': event.event_date,
                'present': present,
                'absent': absent,
                'excused': excused,
                'rate': round(rate, 1),
                'total_marked': total_records
            })
            
            
        return event_stats

    @staticmethod
    def get_member_stats(user_id):
        """
        Return stats for a specific user:
        - Tasks Completed / Total Assigned
        - Attendance Rate
        """
        # Task Stats
        total_assigned = TaskAssignee.query.filter_by(user_id=user_id).count()
        completed = db.session.query(TaskAssignee).join(Task).filter(
            TaskAssignee.user_id == user_id,
            Task.status == 'done'
        ).count()
        
        task_rate = (completed / total_assigned * 100) if total_assigned > 0 else 0
        
        # Attendance Stats
        attendance_records = Attendance.query.filter_by(user_id=user_id).all()
        total_events = len(attendance_records)
        present = sum(1 for a in attendance_records if a.status == 'present')
        
        attendance_rate = (present / total_events * 100) if total_events > 0 else 0
        
        return {
            'tasks_assigned': total_assigned,
            'tasks_completed': completed,
            'task_rate': round(task_rate, 1),
            'attendance_rate': round(attendance_rate, 1),
            'events_attended': present,
            'total_events': total_events
        }
