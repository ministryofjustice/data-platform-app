from django import template

register = template.Library()


@register.simple_tag
def has_project_permission(user, permission: str, project) -> bool:
    """Check whether user has given project permission."""
    return user.has_perm(permission, project)
