GROUP_ANALYST = 'Аналитика'
GROUP_MONITOR = 'Мониторинг'


def user_roles(request):
    user = request.user
    if not user.is_authenticated:
        return {
            'user_is_staff': False,
            'user_is_monitor': False,
            'user_is_analyst': False,
        }
    return {
        'user_is_staff': user.is_staff,
        'user_is_monitor': user.groups.filter(name=GROUP_MONITOR).exists(),
        'user_is_analyst': user.groups.filter(name=GROUP_ANALYST).exists(),
    }
