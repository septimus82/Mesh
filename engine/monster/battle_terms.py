"""Project-configurable battle UI labels and narration templates.

Pure module: no GameWindow, save, or arcade dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, fields


def _render(template: str, **kwargs: object) -> str:
    return template.format(**kwargs)


@dataclass(frozen=True, slots=True)
class BattleTerms:
    """User-facing battle labels and narration templates ({name}-style placeholders)."""

    capture_item_name: str = "Pocket Ball"
    capture_item_plural: str = "Pocket Balls"
    capture_item_menu_label: str = "Ball"
    move_resource_label: str = "PP"
    intro_wild_unknown: str = "Something blocks your path!"
    intro_wild_named: str = "{name} blocks your path!"
    intro_companion: str = "Go, {name}! Your companion stands ready."
    choose_action: str = "Choose an action."
    choose_move: str = "Choose a move."
    choose_item: str = "Choose an item."
    how_respond: str = "How do you respond?"
    cant_catch_trainer: str = "You can't capture a trainer's monster!"
    run_away_safe: str = "You slipped away!"
    presentation_pending: str = "..."
    player_recall: str = "Come back, {name}!"
    player_send_out: str = "{name} takes the field!"
    opponent_send_out: str = "{name} joins the fight!"
    ko: str = "{name} is down!"
    ko_foe: str = "Foe {name} is down!"
    capture_threw_broke_free: str = "You threw a {item}! {name} slipped free!"
    capture_success: str = "{name} was captured!"
    sent_to_box: str = "Sent to the box!"
    sent_to_party: str = "Added {name} to your party!"
    companion_flees: str = "{name} runs away!"
    companion_abandoned: str = "It abandoned you."
    poisoned: str = "{name} was poisoned!"
    poison_damage: str = "{name} is hurt by poison!"
    fell_asleep: str = "{name} fell asleep!"
    woke_up: str = "{name} woke up!"
    asleep_skip: str = "{name} is fast asleep!"
    status_affected: str = "{name} was affected!"
    move_hit: str = "{actor} used {move}! {target} took {damage} damage."
    move_miss: str = "{actor} used {move}, but it missed!"
    nothing_happened: str = "Nothing happened."
    xp_gain: str = "{name} gained {xp} XP!"
    level_up: str = "{name} reached Lv {level}!"
    learn_move: str = "{name} learned {move}!"
    companion_attack: str = "{name} strikes!"
    companion_defend: str = "{name} braces."
    companion_flee_line: str = "{name} runs away!"
    companion_hesitate: str = "{name} hesitates."
    praise_1: str = "You praise {name}."
    praise_2: str = "It looks pleased."
    scold_1: str = "You scold {name}."
    scold_2: str = "It flinches."
    wait_1: str = "You wait calmly."
    wait_2: str = "It watches you."
    defeat_no_fighters: str = "You have no one left who can fight."
    no_capture_items_left: str = "No {plural} left!"

    def format_move_row(self, *, move_id: str, move_type: str, move_pp: int) -> str:
        return f"{move_id} {move_type} {self.move_resource_label} {move_pp}"

    def format_capture_bag_row(self, count: int) -> str:
        return f"{self.capture_item_name} x{count}"

    def format_no_capture_items_left(self) -> str:
        return _render(self.no_capture_items_left, plural=self.capture_item_plural)

    def format_threw_capture_item(self, *, opponent_name: str) -> str:
        return _render(
            self.capture_threw_broke_free,
            item=self.capture_item_name,
            name=opponent_name,
        )

    def format_intro_wild(self, *, name: str) -> str:
        return _render(self.intro_wild_named, name=name)

    def format_intro_companion(self, *, name: str) -> str:
        return _render(self.intro_companion, name=name)

    def format_player_recall(self, *, name: str) -> str:
        return _render(self.player_recall, name=name)

    def format_player_send_out(self, *, name: str) -> str:
        return _render(self.player_send_out, name=name)

    def format_opponent_send_out(self, *, name: str) -> str:
        return _render(self.opponent_send_out, name=name)

    def format_ko(self, *, name: str) -> str:
        return _render(self.ko, name=name)

    def format_ko_foe(self, *, name: str) -> str:
        return _render(self.ko_foe, name=name)

    def format_capture_success(self, *, name: str) -> str:
        return _render(self.capture_success, name=name)

    def format_sent_to_party(self, *, name: str) -> str:
        return _render(self.sent_to_party, name=name)

    def format_companion_flees(self, *, name: str) -> str:
        return _render(self.companion_flees, name=name)

    def format_poisoned(self, *, name: str) -> str:
        return _render(self.poisoned, name=name)

    def format_poison_damage(self, *, name: str) -> str:
        return _render(self.poison_damage, name=name)

    def format_fell_asleep(self, *, name: str) -> str:
        return _render(self.fell_asleep, name=name)

    def format_woke_up(self, *, name: str) -> str:
        return _render(self.woke_up, name=name)

    def format_asleep_skip(self, *, name: str) -> str:
        return _render(self.asleep_skip, name=name)

    def format_status_affected(self, *, name: str) -> str:
        return _render(self.status_affected, name=name)

    def format_move_hit(self, *, actor: str, move: str, target: str, damage: int) -> str:
        return _render(self.move_hit, actor=actor, move=move, target=target, damage=damage)

    def format_move_miss(self, *, actor: str, move: str) -> str:
        return _render(self.move_miss, actor=actor, move=move)

    def format_xp_gain(self, *, name: str, xp: int) -> str:
        return _render(self.xp_gain, name=name, xp=xp)

    def format_level_up(self, *, name: str, level: int) -> str:
        return _render(self.level_up, name=name, level=level)

    def format_learn_move(self, *, name: str, move: str) -> str:
        return _render(self.learn_move, name=name, move=move)

    def format_companion_attack(self, *, name: str) -> str:
        return _render(self.companion_attack, name=name)

    def format_companion_defend(self, *, name: str) -> str:
        return _render(self.companion_defend, name=name)

    def format_companion_flee_line(self, *, name: str) -> str:
        return _render(self.companion_flee_line, name=name)

    def format_companion_hesitate(self, *, name: str) -> str:
        return _render(self.companion_hesitate, name=name)

    def format_praise_1(self, *, name: str) -> str:
        return _render(self.praise_1, name=name)

    def format_scold_1(self, *, name: str) -> str:
        return _render(self.scold_1, name=name)

    def all_template_values(self) -> tuple[str, ...]:
        return tuple(str(getattr(self, field.name)) for field in fields(self))


DEFAULT_BATTLE_TERMS = BattleTerms()

POKEMON_CLONE_DENYLIST = (
    "wild",
    "appeared",
    "sent out",
    "fainted",
    "gotcha",
    "super effective",
)
