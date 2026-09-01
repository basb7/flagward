"""
Tests for `tenancy.slugs.unique_key`, the single definition of "turn a name
somebody typed into a key nobody has to type".

The helper is shared by `ProjectSerializer` and `EnvironmentSerializer`, so
its edges are pinned here once rather than twice at the API level: the empty
slug, the collision suffix, and the `max_length` boundary a 255-character
`SlugField` imposes.
"""
import pytest

from core_flags.models import Environment
from tenancy.models import Project
from tenancy.slugs import EMPTY_SLUG_FALLBACK, unique_key


@pytest.mark.django_db
class TestUniqueKeyDerivation:
    def test_derives_a_slug_from_the_name(self, organization):
        key = unique_key(
            base_name="Mobile App",
            queryset=Project.objects.filter(organization=organization),
        )

        assert key == "mobile-app"

    def test_name_that_slugifies_to_nothing_falls_back_to_a_valid_key(self, organization):
        key = unique_key(
            base_name="🚀🚀🚀",
            queryset=Project.objects.filter(organization=organization),
        )

        assert key == EMPTY_SLUG_FALLBACK
        assert key != ""

    def test_punctuation_only_name_falls_back_too(self, organization):
        key = unique_key(
            base_name="!!! ??? ...",
            queryset=Project.objects.filter(organization=organization),
        )

        assert key == EMPTY_SLUG_FALLBACK


@pytest.mark.django_db
class TestUniqueKeyCollisions:
    def test_appends_a_numeric_suffix_when_the_slug_is_taken(self, organization):
        Project.objects.create(organization=organization, name="Mobile App", key="mobile-app")

        key = unique_key(
            base_name="Mobile App",
            queryset=Project.objects.filter(organization=organization),
        )

        assert key == "mobile-app-2"

    def test_walks_the_suffix_until_it_finds_a_free_key(self, organization):
        for taken in ("mobile-app", "mobile-app-2", "mobile-app-3"):
            Project.objects.create(organization=organization, name="Mobile App", key=taken)

        key = unique_key(
            base_name="Mobile App",
            queryset=Project.objects.filter(organization=organization),
        )

        assert key == "mobile-app-4"

    def test_fallback_key_collides_and_gets_a_suffix_like_any_other(self, organization):
        Project.objects.create(organization=organization, name="🚀", key=EMPTY_SLUG_FALLBACK)

        key = unique_key(
            base_name="🎉",
            queryset=Project.objects.filter(organization=organization),
        )

        assert key == f"{EMPTY_SLUG_FALLBACK}-2"

    def test_collisions_are_scoped_to_the_queryset_it_is_given(self, organization, make_project):
        other_organization = make_project(name="Other").organization
        Project.objects.create(organization=other_organization, name="Mobile App", key="mobile-app")

        key = unique_key(
            base_name="Mobile App",
            queryset=Project.objects.filter(organization=organization),
        )

        assert key == "mobile-app"

    def test_treats_already_attempted_keys_as_taken(self, organization):
        key = unique_key(
            base_name="Mobile App",
            queryset=Project.objects.filter(organization=organization),
            taken={"mobile-app"},
        )

        assert key == "mobile-app-2"

    def test_honours_a_custom_field_name_and_a_foreign_model(self, project):
        Environment.objects.create(project=project, name="Production", key="production")

        key = unique_key(
            base_name="Production",
            queryset=Environment.objects.filter(project=project),
            field="key",
        )

        assert key == "production-2"


@pytest.mark.django_db
class TestUniqueKeyMaxLength:
    def test_truncates_a_name_longer_than_max_length(self, organization):
        key = unique_key(
            base_name="a" * 300,
            queryset=Project.objects.filter(organization=organization),
        )

        assert len(key) == 255
        assert key == "a" * 255

    def test_makes_room_for_the_suffix_at_the_max_length_boundary(self, organization):
        # A 255-character name slugifies to exactly `max_length` characters,
        # so the collision suffix has nowhere to go unless the base is cut
        # back to fit -- the case a naive `f"{slug}-{n}"` silently overflows
        # the SlugField with.
        name = "a" * 255
        Project.objects.create(organization=organization, name=name, key="a" * 255)

        key = unique_key(
            base_name=name,
            queryset=Project.objects.filter(organization=organization),
        )

        assert len(key) == 255
        assert key == "a" * 253 + "-2"

    def test_never_leaves_a_trailing_hyphen_after_truncation(self, organization):
        key = unique_key(
            base_name="ab " * 40,  # slugifies to "ab-ab-ab-...", hyphen at every odd cut
            queryset=Project.objects.filter(organization=organization),
            max_length=9,
        )

        assert key == "ab-ab-ab"
