import pytest

from src.scene import Mobject, Scene


def test_replace_swaps_a_top_level_object_in_place() -> None:
    scene = Scene()
    circle, square, label = Mobject("circle"), Mobject("square"), Mobject("label")
    scene.add(circle, label)
    scene.replace(circle, square)
    assert scene.mobjects == [square, label]


def test_replace_finds_an_object_inside_a_group() -> None:
    scene = Scene()
    circle, square = Mobject("circle"), Mobject("square")
    group = Mobject("group", circle)
    scene.add(group)
    scene.replace(circle, square)
    assert group.submobjects == [square]


def test_replace_rejects_an_object_not_in_the_scene() -> None:
    scene = Scene()
    with pytest.raises(ValueError, match="Could not find"):
        scene.replace(Mobject("circle"), Mobject("square"))


def test_no_duplicate_reference_when_the_target_is_already_on_screen() -> None:
    scene = Scene()
    circle, square = Mobject("circle"), Mobject("square")
    scene.add(circle, square)
    scene.replace(circle, square)
    assert scene.mobjects == [square]


def test_no_duplicate_reference_inside_a_group() -> None:
    scene = Scene()
    circle, square = Mobject("circle"), Mobject("square")
    group = Mobject("group", circle, square)
    scene.add(group)
    scene.replace(circle, square)
    assert group.submobjects == [square]
