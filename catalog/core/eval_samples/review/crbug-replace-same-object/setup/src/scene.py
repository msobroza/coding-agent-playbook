"""A scene keeps an ordered list of drawable objects; a group nests other objects."""

from __future__ import annotations


class Mobject:
    """A drawable object; its ``submobjects`` are the objects it groups."""

    def __init__(self, name: str, *submobjects: Mobject) -> None:
        self.name = name
        self.submobjects: list[Mobject] = list(submobjects)

    def __repr__(self) -> str:
        return f"Mobject({self.name!r})"


class Scene:
    """The objects on screen, drawn in list order."""

    def __init__(self) -> None:
        self.mobjects: list[Mobject] = []

    def add(self, *mobjects: Mobject) -> None:
        """Put each object on screen once, on top of the ones already there."""
        for mobject in mobjects:
            if mobject not in self.mobjects:
                self.mobjects.append(mobject)

    def replace(self, old_mobject: Mobject, new_mobject: Mobject) -> None:
        """Put ``new_mobject`` where ``old_mobject`` is, at top level or inside a group.

        A transform that turns one object into another ends with this call.
        """

        def replace_in_list(mobj_list: list[Mobject], old_m: Mobject, new_m: Mobject) -> bool:
            # Avoid duplicate references to the same object in the scene
            if new_m in mobj_list:
                mobj_list.remove(new_m)

            # Breadth-first: top-level objects are the most common targets, and
            # some groups nest deeply.
            for i in range(len(mobj_list)):
                if mobj_list[i] == old_m:
                    mobj_list[i] = new_m
                    return True
            for mobj in mobj_list:
                if replace_in_list(mobj.submobjects, old_m, new_m):
                    return True
            return False

        if not replace_in_list(self.mobjects, old_mobject, new_mobject):
            raise ValueError(f"Could not find {old_mobject} in the scene")
