from model_bakery import baker

from projects.forms import ProjectCreateForm


class TestProjectCreateForm:
    def test_business_unit_choices_are_sorted_alphabetically(self, db):
        baker.make("projects.BusinessUnit", name="Z Test Unit", code="ZZZ_TEST")
        baker.make("projects.BusinessUnit", name="A Test Unit", code="AAA_TEST")
        baker.make("projects.BusinessUnit", name="B Test Unit", code="BBB_TEST")

        form = ProjectCreateForm()

        test_business_unit_names = [
            business_unit.name
            for business_unit in form.fields["business_unit"].queryset
            if business_unit.code.endswith("_TEST")
        ]
        assert test_business_unit_names == ["A Test Unit", "B Test Unit", "Z Test Unit"]
