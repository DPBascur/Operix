from django.core.exceptions import ValidationError

MAX_PASSWORD_LENGTH = 256


class MaximumPasswordLengthValidator:
    def validate(self, password, user=None):
        if len(password) > MAX_PASSWORD_LENGTH:
            raise ValidationError(self.get_help_text(), code="password_too_long")

    def get_help_text(self):
        return f"La contraseña debe tener como máximo {MAX_PASSWORD_LENGTH} caracteres."
