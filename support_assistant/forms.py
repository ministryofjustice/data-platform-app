from django import forms
from django.conf import settings


class QuestionForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_length = settings.SUPPORT_ASSISTANT_MAX_QUESTION_LENGTH
        self.fields["question"] = forms.CharField(
            label="Your question",
            max_length=self.max_length,
            error_messages={
                "required": "Enter a question",
                "max_length": f"Question must be {self.max_length} characters or fewer",
            },
        )


class FeedbackForm(forms.Form):
    helpful = forms.TypedChoiceField(
        choices=[("yes", "Yes"), ("no", "No")],
        coerce=lambda value: value == "yes",
        error_messages={"required": "Choose yes or no", "invalid_choice": "Choose yes or no"},
    )
    comment = forms.CharField(
        label="What were you looking for? (optional)",
        required=False,
        max_length=1000,
        error_messages={"max_length": "Comment must be 1000 characters or fewer"},
    )
