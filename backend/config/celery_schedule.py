from celery.schedules import crontab

beat_schedule: dict[str, dict[str, object]] = {
    "prune-stale-fcm-registrations": {
        "task": "backend.apps.notifications.tasks.prune_stale_fcm_registrations",
        "schedule": crontab(minute=0, hour=3),
        "options": {
            "queue": "periodic",
            "expires": 6 * 60 * 60,
        },
    },
}
