class CategoryNotFoundError(Exception):
    pass


class ParentCategoryNotFoundError(Exception):
    pass


class DuplicateCategorySlugError(Exception):
    pass


class CategoryHierarchyError(Exception):
    pass


class CategoryDeleteConflictError(Exception):
    pass


class CategoryFilterConflictError(ValueError):
    pass
