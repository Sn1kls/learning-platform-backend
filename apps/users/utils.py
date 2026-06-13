import csv
import logging
import threading
import typing

from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied
from django.core.mail import EmailMessage
from django.template.loader import get_template
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _

from apps.modules.exceptions import (
    EducationNotStartedError,
    ModuleClosedError,
    PreviousLessonNotCompletedError,
)
from apps.modules.models import Lesson, Module, UserLessonProgress
from apps.users.exceptions import UserHasNotApprovedRequirementsError
from apps.users.models import CHAT_INVITATION_GENERAL_AUDIENCE, ChatInvitation, User
from config import settings

if typing.TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser  # noqa
    from django.db.models import QuerySet

    from apps.users.models import UserGroup  # noqa

logger = logging.getLogger(__name__)


def generate_user_token(user: "User | AbstractBaseUser") -> tuple[str, str]:
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return uidb64, token


def verify_user_token(uidb64: str, token: str) -> User | None:
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist) as e:
        logger.error(f"{e.__class__.__name__}: {e}")
        return None

    if default_token_generator.check_token(user, token):
        return user
    return None


def build_activation_url(frontend_url: str, uidb64: str, token: str) -> str:
    base = frontend_url.rstrip("/")
    return f"{base}/activate/{uidb64}-{token}"


def build_reset_url(frontend_url: str, uidb64: str, token: str) -> str:
    base = frontend_url.rstrip("/")
    return f"{base}/reset-password/{uidb64}-{token}"


def render_activation_email(user: "User | AbstractBaseUser", activation_url: str) -> str:
    template = get_template("emails/activation_email.html")
    return template.render({"user": user, "activation_url": activation_url})


def render_reset_email(user: "User | AbstractBaseUser", reset_url: str) -> str:
    template = get_template("emails/password_reset_email.html")
    return template.render({"user": user, "reset_url": reset_url})


def render_chat_invitation_email(
    user: "User | AbstractBaseUser",
    personal_invitation: ChatInvitation,
    general_invitation: ChatInvitation | None = None,
) -> str:
    template = get_template("emails/chat_invitation_email.html")
    return template.render(
        {
            "user": user,
            "personal_invitation": personal_invitation,
            "general_invitation": general_invitation,
        }
    )


def __get_chat_invitation(user: "User | AbstractBaseUser", audience: str) -> ChatInvitation | None:
    group = user.user_groups.first()
    if group:
        chat_invitation = ChatInvitation.objects.filter(
            group=group, audience=audience, is_active=True
        ).first()
        if chat_invitation:
            return chat_invitation
    return None

def get_user_chat_invitation(user: "User | AbstractBaseUser") -> ChatInvitation | None:
    return __get_chat_invitation(user, user.age_group)

def get_general_chat_invitation(user: "User | AbstractBaseUser") -> ChatInvitation | None:
    chat_invitation = __get_chat_invitation(user, CHAT_INVITATION_GENERAL_AUDIENCE)
    if chat_invitation:
        return chat_invitation
    return ChatInvitation.objects.filter(
        group__isnull=True, audience=CHAT_INVITATION_GENERAL_AUDIENCE, is_active=True
    ).first()


def __check_has_user_approved_requirements(user: "User | AbstractBaseUser") -> bool:
    if not user.has_approved_requirements:
        raise UserHasNotApprovedRequirementsError()
    return True


def __check_module_access(user: "User | AbstractBaseUser", module_id: int) -> bool:
    group: "UserGroup" = user.user_groups.first()

    if not group:
        raise PermissionDenied(_("You are not member of any group."))

    module = Module.active.get(pk=module_id)
    if not group.is_module_available(module.order):
        unlock_date = group.get_module_unlock_date(module.order)
        raise ModuleClosedError(opening_date=unlock_date)

    return True


def __check_lesson_access(user: "User | AbstractBaseUser", module_id: int, lesson_id: int) -> bool:
    __check_module_access(user, module_id)

    current_lesson = Lesson.active.get(
        pk=lesson_id,
        module_fk_id=module_id,
    )

    last_completed_lesson = (
        UserLessonProgress.objects.filter(
            user_fk=user,
            is_completed=True,
        )
        .select_related("lesson_fk", "lesson_fk__module_fk")
        .order_by(
            "-lesson_fk__module_fk__order",
            "-lesson_fk__order",
        )
        .first()
    )

    if not last_completed_lesson:
        first_module = Module.active.order_by("order").first()
        first_lesson = Lesson.active.filter(module_fk=first_module).order_by("order").first()

        if current_lesson != first_lesson:
            raise EducationNotStartedError()

    else:
        last_lesson = last_completed_lesson.lesson_fk

        current_position = (
            current_lesson.module_fk.order,
            current_lesson.order,
            current_lesson.id,
        )
        last_completed_position = (
            last_lesson.module_fk.order,
            last_lesson.order,
            last_lesson.id,
        )

        if current_position <= last_completed_position:
            return True

        next_lesson = (
            Lesson.active.filter(
                module_fk=last_lesson.module_fk,
                order__gt=last_lesson.order,
            )
            .order_by("order")
            .first()
        )

        if not next_lesson:
            next_module = (
                Module.active.filter(
                    order__gt=last_lesson.module_fk.order,
                )
                .order_by("order")
                .first()
            )

            if next_module:
                next_lesson = Lesson.active.filter(module_fk=next_module).order_by("order").first()

        is_already_completed = UserLessonProgress.objects.filter(
            user_fk=user,
            lesson_fk=current_lesson,
            is_completed=True,
        ).exists()

        if not is_already_completed and current_lesson != next_lesson:
            raise PreviousLessonNotCompletedError()

    return True


def send_email(user_email: str, html_content: str, email_title: str) -> None:
    logger.info(f"Sending email to {user_email}")
    email = EmailMessage(
        subject=force_str(email_title),
        body=force_str(html_content),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user_email],
    )
    email.content_subtype = "html"
    email.send(fail_silently=False)


def send_activation_email(
    user: "User | AbstractBaseUser",
    frontend_url: str,
    email_title: str = _("Activate your account"),
) -> bool:
    try:
        logger.info(f"Trying to send activation email for user for {user.email}.")
        uidb64, token = generate_user_token(user)
        activation_url = build_activation_url(frontend_url, uidb64, token)
        html_content = render_activation_email(user, activation_url)
        threading.Thread(
            target=send_email,
            args=(user.email, html_content, force_str(email_title)),
            daemon=True,
        ).start()
        return True
    except Exception as e:
        logger.error(f"{e.__class__.__name__}Failed to send activation email: {e!r}")
        return False


def send_reset_password_email(
    user: "User | AbstractBaseUser",
    frontend_url: str,
    email_title: str = _("Reset your password"),
) -> bool:
    try:
        logger.info(f"Trying to send password reset email for user {user.email}.")
        uidb64, token = generate_user_token(user)
        reset_url = build_reset_url(frontend_url, uidb64, token)
        html_content = render_reset_email(user, reset_url)
        threading.Thread(
            target=send_email,
            args=(user.email, html_content, force_str(email_title)),
            daemon=True,
        ).start()
        return True
    except Exception as e:
        logger.error(f"{e.__class__.__name__} Failed to send reset email: {e!r}")
        return False


def send_chat_invitation_email(
    user: "User | AbstractBaseUser",
    email_title: str = _("Your Learning Platform chat invitation"),
) -> bool:
    try:
        logger.info(f"Trying to send chat invitation email for user {user.email}.")
        personal_invitation = get_user_chat_invitation(user)
        if not personal_invitation:
            logger.error(f"No active personal chat invitation found for age group '{user.age_group}'.")
            return False

        general_invitation = get_general_chat_invitation(user)
        subject = force_str(email_title)
        html_content = render_chat_invitation_email(user, personal_invitation, general_invitation)
        threading.Thread(
            target=send_email,
            args=(user.email, html_content, subject),
            daemon=True,
        ).start()
        return True
    except Exception as e:
        logger.error(f"{e.__class__.__name__} Failed to send chat invitation email: {e!r}")
        return False


def write_to_csv(*, source: typing.Any, queryset: "QuerySet", fields: list[str], is_pretty_display: bool = True):
    writer = csv.writer(source)
    writer.writerow(fields)

    for obj in queryset:
        rows_data = []
        for field in fields:
            value = getattr(obj, field)
            display_method_name = f"get_{field}_display"

            if is_pretty_display and hasattr(obj, display_method_name):
                value = getattr(obj, display_method_name)()

            if callable(value):
                value = value()

            rows_data.append(value if value is not None else "-")
        writer.writerow(rows_data)
