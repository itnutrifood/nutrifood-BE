from uuid import UUID


class SubscriptionPlanNotFoundError(Exception):
    pass


class DuplicateSubscriptionPlanSlugError(Exception):
    pass


class SubscriptionPlanDeleteConflictError(Exception):
    pass


class UserSubscriptionNotFoundError(Exception):
    pass


class ActiveSubscriptionConflictError(Exception):
    def __init__(self, subscription_plan_id: UUID) -> None:
        self.subscription_plan_id = subscription_plan_id
        super().__init__("User already has an active subscription")
