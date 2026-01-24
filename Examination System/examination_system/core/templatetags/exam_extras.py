from django import template


register = template.Library()


@register.filter
def get_item(subjects, subject_id):
    for subject in subjects:
        if str(subject.id) == str(subject_id):
            return subject.name
    return ""

