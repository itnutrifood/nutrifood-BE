from celery.schedules import crontab

beat_schedule: dict[str, dict[str, object]] = {
    "refresh-public-statistics-cache": {
        "task": "backend.apps.statistics.tasks.refresh_statistics_cache",
        "schedule": crontab(minute=0, hour=0),
        "options": {
            "queue": "periodic",
            "expires": 6 * 60 * 60,
        },
    },
    "prune-stale-fcm-registrations": {
        "task": "backend.apps.notifications.tasks.prune_stale_fcm_registrations",
        "schedule": crontab(minute=0, hour=3),
        "options": {
            "queue": "periodic",
            "expires": 6 * 60 * 60,
        },
    },
}
