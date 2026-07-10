from django.db import migrations


def create_business_units(apps, schema_editor):
    BusinessUnit = apps.get_model("projects", "BusinessUnit")
    BusinessUnit.objects.bulk_create(
        [
            BusinessUnit(name="HM Prison and Probation Service", code="HMPPS"),
            BusinessUnit(name="Office of the Public Guardian", code="OPG"),
            BusinessUnit(name="Legal Aid Agency", code="LAA"),
            BusinessUnit(name="Central Digital", code="Central Digital"),
            BusinessUnit(name="Technology Services", code="Technology Services"),
            BusinessUnit(name="HM Courts and Tribunals Service", code="HMCTS"),
            BusinessUnit(name="Criminal Injuries Compensation Authority", code="CICA"),
            BusinessUnit(name="Office of the CTO", code="OCTO"),
            BusinessUnit(name="Youth Justice Board", code="YJB"),
        ]
    )


def reverse_create_business_units(apps, schema_editor):
    BusinessUnit = apps.get_model("projects", "BusinessUnit")
    BusinessUnit.objects.filter(
        code__in=[
            "HMPPS",
            "OPG",
            "LAA",
            "Central Digital",
            "Technology Services",
            "HMCTS",
            "CICA",
            "OCTO",
            "YJB",
        ]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0006_remove_historicalproject_slug_remove_project_slug"),
    ]

    operations = [
        migrations.RunPython(create_business_units, reverse_create_business_units),
    ]
