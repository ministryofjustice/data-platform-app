from django.db import migrations

BUSINESS_UNITS = [
    ("CICA", "cica"),
    ("Central Digital", "central_digital"),
    ("HMCTS", "hmcts"),
    ("HMPPS", "hmpps"),
    ("LAA", "laa"),
    ("OCTO", "octo"),
    ("OPG", "opg"),
    ("Technology Services", "technology_services"),
    ("YJB", "yjb"),
]


def seed_business_units(apps, schema_editor):
    business_unit_model = apps.get_model("projects", "BusinessUnit")

    for name, code in BUSINESS_UNITS:
        business_unit_model.objects.update_or_create(
            code=code,
            defaults={"name": name},
        )


def unseed_business_units(apps, schema_editor):
    business_unit_model = apps.get_model("projects", "BusinessUnit")
    business_unit_model.objects.filter(code__in=[code for _, code in BUSINESS_UNITS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0002_projectmember"),
    ]

    operations = [
        migrations.RunPython(seed_business_units, unseed_business_units),
    ]
