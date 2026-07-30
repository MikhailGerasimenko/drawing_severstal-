"""Универсальная классификация размерных токенов для тел вращения."""
from __future__ import annotations

import re
from typing import Any, Optional

INTERNAL_FIT_RE = re.compile(r"H\d+")
SHAFT_FIT_RE = re.compile(r"(?<![A-Za-zА-Яа-я])([a-z]{1,2}\d+)(?![A-Za-zА-Яа-я])")
EXTERNAL_FIT_RE = re.compile(r"[bcefghjs]\d+", re.IGNORECASE)
DIAMETER_VALUE_RE = re.compile(r"[Ø∅]\s*(\d+(?:[,.]\d+)?)", re.IGNORECASE)
PITCH_ANGLE_RE = re.compile(r"(?:\d+\s*[xх×]\s*)?\d+\s*°", re.IGNORECASE)
LENGTH_TOLERANCE_RE = re.compile(r"^[LH]\s*-\s*\d", re.IGNORECASE)
LENGTH_MM_RE = re.compile(r"^\d+(?:[,.]\d+)?\s*(?:±|\+|-)", re.IGNORECASE)
DIMENSION_LABEL_RE = re.compile(r"^[lL]\d+$")
THREAD_RE = re.compile(r"^M\d+(?:[,.]\d+)?(?:-\d+[A-Za-z])?", re.IGNORECASE)
UNILATERAL_PLUS_RE = re.compile(r"[Ø∅][^+\-]*\+\s*\d", re.IGNORECASE)
CONE_ANGLE_RE = re.compile(r"^\d+(?:,\d+)?°(?:±\d+(?:,\d+)?(?:['′]|°)?)?$")
HOLE_QTY_RE = re.compile(r"(\d+)\s*отв\.?\s*[Ø∅]\s*(\d+(?:[,.]\d+)?)", re.IGNORECASE)


def _parse_diameter_mm(normalized: str) -> float:
    match = DIAMETER_VALUE_RE.search(normalized)
    if not match:
        return 0.0
    return float(match.group(1).replace(",", "."))


def _has_shaft_fit(normalized: str) -> bool:
    if INTERNAL_FIT_RE.search(normalized):
        return False
    return bool(SHAFT_FIT_RE.search(normalized))


def _has_internal_fit(normalized: str) -> bool:
    return bool(INTERNAL_FIT_RE.search(normalized))


def _is_diameter_token(token: dict[str, Any]) -> bool:
    return bool(DIAMETER_VALUE_RE.search(token.get("normalized", "")))


def _is_dimension_label(normalized: str) -> bool:
    return bool(DIMENSION_LABEL_RE.match(normalized))


def _is_length_token(normalized: str) -> bool:
    if _is_dimension_label(normalized):
        return False
    if LENGTH_TOLERANCE_RE.search(normalized):
        return True
    return bool(LENGTH_MM_RE.search(normalized))


def _fact(
    feature_type: str,
    value: Any,
    *,
    label: str,
    source: dict[str, Any],
    confidence: str = "medium",
    note: str = "",
) -> dict[str, Any]:
    item = {
        "type": feature_type,
        "label": label,
        "value": value,
        "source": source,
        "confidence": confidence,
    }
    if note:
        item["note"] = note
    return item


def _has_unilateral_plus(normalized: str) -> bool:
    return bool(UNILATERAL_PLUS_RE.search(normalized))


def apply_generic_dimension_classification(
    features: dict[str, Any],
    tokens: list[dict[str, Any]],
    classified: set[str],
    text_evidence: list[str],
) -> None:
    """Дополнить external_contour / internal_system / special_elements эвристиками по посадкам."""
    if not tokens:
        return

    available = [token for token in tokens if token["normalized"].lower() not in classified]
    diameters = [token for token in available if _is_diameter_token(token)]

    unilateral = [token for token in diameters if _has_unilateral_plus(token["normalized"])]
    internal = [
        token
        for token in diameters
        if _has_internal_fit(token["normalized"]) and token not in unilateral
    ]
    external = [
        token
        for token in diameters
        if _has_shaft_fit(token["normalized"]) and token not in unilateral
    ]
    plain = [
        token
        for token in diameters
        if token not in internal and token not in external and token not in unilateral
    ]

    _classify_unilateral_holes(features, unilateral, classified)
    _classify_pitch_hole_groups(features, diameters, classified, text_evidence)
    _classify_qty_holes(features, diameters, classified, text_evidence)
    _classify_external_shafts(features, external, classified)
    _classify_internal_holes(features, internal, classified)
    _classify_plain_diameters(features, plain, classified)
    _classify_letter_parameters(features, available, classified, text_evidence)
    _classify_threads(features, available, classified)
    _classify_lengths(features, available, classified, text_evidence)
    _classify_cone_angles(features, available, classified, text_evidence)
    _classify_fillets(features, available, classified)
    _classify_chamfers_generic(features, available, classified)
    _classify_window_and_corner_holes(features, available, classified, text_evidence)


def _mark(classified: set[str], *tokens: Optional[dict[str, Any]]) -> None:
    for token in tokens:
        if token:
            classified.add(token["normalized"].lower())


def _classify_unilateral_holes(
    features: dict[str, Any],
    unilateral: list[dict[str, Any]],
    classified: set[str],
) -> None:
    if not unilateral:
        return
    ordered = sorted(unilateral, key=lambda item: _parse_diameter_mm(item["normalized"]), reverse=True)
    for index, token in enumerate(ordered[:4]):
        if token["normalized"].lower() in classified:
            continue
        label = "Основное осевое отверстие" if index == 0 else "Внутренняя ступень/расточка"
        fact_type = "main_axial_hole" if index == 0 else "counterbore_or_stepped_hole"
        if index == 0 and any(item.get("type") in {"main_axial_hole", "main_axial_hole_candidate"} for item in features["internal_system"]):
            fact_type = "counterbore_or_stepped_hole"
            label = "Внутренняя ступень/расточка"
        features["internal_system"].append(
            _fact(
                fact_type,
                token["value"],
                label=label,
                source=token["source"],
                confidence="high",
                note="Односторонний допуск +… подтверждает отверстие; не формулировать как «кандидат».",
            )
        )
        _mark(classified, token)


def _classify_qty_holes(
    features: dict[str, Any],
    diameters: list[dict[str, Any]],
    classified: set[str],
    text_evidence: list[str],
) -> None:
    if any(item.get("type") == "axial_hole_pattern" for item in features["special_elements"]):
        return
    qty_match = None
    for item in text_evidence:
        qty_match = HOLE_QTY_RE.search(item)
        if qty_match:
            break
    if not qty_match:
        return
    quantity = int(qty_match.group(1))
    hole_mm = float(qty_match.group(2).replace(",", "."))
    hole = None
    for token in diameters:
        if abs(_parse_diameter_mm(token["normalized"]) - hole_mm) < 0.05:
            hole = token
            break
    if not hole:
        return
    pitch_candidates = [
        token
        for token in diameters
        if token is not hole
        and not _has_shaft_fit(token["normalized"])
        and _parse_diameter_mm(token["normalized"]) > hole_mm
    ]
    pitch_candidates.sort(key=lambda item: _parse_diameter_mm(item["normalized"]))
    value: dict[str, Any] = {
        "quantity": quantity,
        "hole_diameter": hole["value"],
    }
    pitch = pitch_candidates[0] if pitch_candidates else None
    if pitch:
        value["pitch_diameter"] = pitch["value"]
    # Глубина «10» рядом с отверстиями — частый паттерн на чертежах.
    depth_hint = next(
        (
            item
            for item in text_evidence
            if re.fullmatch(r"10", item.strip()) or re.search(r"глуб\.?\s*10", item, re.I)
        ),
        None,
    )
    if depth_hint:
        value["depth"] = "10"
    features["special_elements"].append(
        _fact(
            "axial_hole_pattern",
            value,
            label="Группа осевых отверстий",
            source=hole["source"],
            confidence="high",
            note="Распознано по подписи «N отв.Ø…».",
        )
    )
    _mark(classified, hole, pitch)


def _classify_pitch_hole_groups(
    features: dict[str, Any],
    diameters: list[dict[str, Any]],
    classified: set[str],
    text_evidence: list[str],
) -> None:
    hole_tokens = [token for token in diameters if _has_internal_fit(token["normalized"])]
    pitch_candidates = [
        token
        for token in diameters
        if not _has_internal_fit(token["normalized"])
        and not _has_shaft_fit(token["normalized"])
        and _parse_diameter_mm(token["normalized"]) > 0
    ]
    has_angle = any(PITCH_ANGLE_RE.search(item) for item in text_evidence)
    has_qty = any(re.search(r"\b3\b", item) and re.search(r"отв|шт|×", item, re.I) for item in text_evidence)

    if any(item.get("type") == "axial_hole_pattern" for item in features["special_elements"]):
        return
    if not hole_tokens or not pitch_candidates or not (has_angle or has_qty):
        return

    pitch_candidates.sort(key=lambda item: _parse_diameter_mm(item["normalized"]), reverse=True)
    pitch = pitch_candidates[0]
    hole = max(hole_tokens, key=lambda item: _parse_diameter_mm(item["normalized"]))
    value: dict[str, Any] = {
        "pitch_diameter": pitch["value"],
        "hole_diameter": hole["value"],
    }
    for item in text_evidence:
        angle = re.search(r"(\d+)\s*[xх×]\s*(\d+)\s*°", item)
        if angle:
            value["angular_spacing"] = f"{angle.group(2)}°"
            break
    if has_qty:
        value["quantity"] = 3

    features["special_elements"].append(
        _fact(
            "axial_hole_pattern",
            value,
            label="Группа осевых отверстий",
            source=pitch["source"],
            confidence="medium",
            note="Классифицировано по сочетанию делительного Ø, отверстий H-посадки и углового шага.",
        )
    )
    _mark(classified, pitch, hole)


def _classify_external_shafts(
    features: dict[str, Any],
    external: list[dict[str, Any]],
    classified: set[str],
) -> None:
    if not external:
        return
    ordered = sorted(external, key=lambda item: _parse_diameter_mm(item["normalized"]), reverse=True)
    main = ordered[0]
    if not any(item.get("type") == "outer_diameter" for item in features["external_contour"]):
        features["external_contour"].append(
            _fact(
                "outer_diameter",
                main["value"],
                label="Основной наружный диаметр",
                source=main["source"],
                confidence="high",
            )
        )
        features["overall"]["max_diameter"] = main["value"]
        _mark(classified, main)

    for step in ordered[1:4]:
        if step["normalized"].lower() in classified:
            continue
        features["external_contour"].append(
            _fact(
                "external_step_diameter",
                step["value"],
                label="Наружная ступень",
                source=step["source"],
                confidence="medium",
            )
        )
        _mark(classified, step)


def _classify_internal_holes(
    features: dict[str, Any],
    internal: list[dict[str, Any]],
    classified: set[str],
) -> None:
    if not internal:
        return
    outer_d = 0.0
    for fact in features.get("external_contour", []):
        if fact.get("type") == "outer_diameter":
            outer_d = _parse_diameter_mm(str(fact.get("value", "")))
            break

    # H-посадка на «толстом» диаметре при наличии меньшего отверстия часто наружная ступень (втулки/вставки).
    hole_like = [
        token
        for token in internal
        if _parse_diameter_mm(token["normalized"]) < (outer_d * 0.45 if outer_d else 1e9)
    ]
    remaining: list[dict[str, Any]] = []
    for token in internal:
        diameter = _parse_diameter_mm(token["normalized"])
        if outer_d and hole_like and diameter >= outer_d * 0.55:
            features["external_contour"].append(
                _fact(
                    "external_step_diameter",
                    token["value"],
                    label="Наружная ступень (посадка H)",
                    source=token["source"],
                    confidence="medium",
                    note="Крупный Ø с H-посадкой отнесён к наружному контуру при наличии меньшего отверстия; проверь по разрезу.",
                )
            )
            _mark(classified, token)
        else:
            remaining.append(token)
    internal = remaining
    if not internal:
        return

    ordered = sorted(internal, key=lambda item: _parse_diameter_mm(item["normalized"]), reverse=True)
    main = ordered[0]
    if not any(item.get("type") in {"main_axial_hole", "main_axial_hole_candidate"} for item in features["internal_system"]):
        features["internal_system"].append(
            _fact(
                "main_axial_hole",
                main["value"],
                label="Основное осевое отверстие",
                source=main["source"],
                confidence="medium",
            )
        )
        _mark(classified, main)

    for extra in ordered[1:4]:
        if extra["normalized"].lower() in classified:
            continue
        features["internal_system"].append(
            _fact(
                "counterbore_or_stepped_hole",
                extra["value"],
                label="Внутренняя ступень/расточка",
                source=extra["source"],
                confidence="medium",
            )
        )
        _mark(classified, extra)


def _classify_plain_diameters(
    features: dict[str, Any],
    plain: list[dict[str, Any]],
    classified: set[str],
) -> None:
    if not plain:
        return
    ordered = sorted(plain, key=lambda item: _parse_diameter_mm(item["normalized"]), reverse=True)
    current_outer = next(
        (fact for fact in features["external_contour"] if fact.get("type") == "outer_diameter"),
        None,
    )
    if current_outer and ordered:
        largest = ordered[0]
        largest_d = _parse_diameter_mm(largest["normalized"])
        current_d = _parse_diameter_mm(str(current_outer.get("value", "")))
        if largest_d > current_d + 0.01:
            current_outer["type"] = "external_step_diameter"
            current_outer["label"] = "Наружная ступень / справочный Ø"
            current_outer["confidence"] = current_outer.get("confidence", "medium")
            features["external_contour"].insert(
                0,
                _fact(
                    "outer_diameter",
                    largest["value"],
                    label="Основной наружный диаметр",
                    source=largest["source"],
                    confidence="medium",
                    note="Наибольший Ø без посадки; меньшие посадочные Ø — ступени.",
                ),
            )
            features["overall"]["max_diameter"] = largest["value"]
            _mark(classified, largest)
            ordered = ordered[1:]

    if not any(item.get("type") == "outer_diameter" for item in features["external_contour"]) and ordered:
        main = ordered[0]
        features["external_contour"].append(
            _fact(
                "outer_diameter",
                main["value"],
                label="Основной наружный диаметр",
                source=main["source"],
                confidence="medium",
                note="Посадка не указана; определено как наружный Ø по величине.",
            )
        )
        features["overall"]["max_diameter"] = main["value"]
        _mark(classified, main)
        ordered = ordered[1:]

    outer_d = 0.0
    for fact in features["external_contour"]:
        if fact.get("type") == "outer_diameter":
            outer_d = _parse_diameter_mm(str(fact.get("value", "")))
            break

    for token in ordered:
        if token["normalized"].lower() in classified:
            continue
        diameter = _parse_diameter_mm(token["normalized"])
        # Близкий к наружному «голый» Ø — справочный/ступень, не отверстие.
        if outer_d and diameter >= outer_d * 0.85:
            features["external_contour"].append(
                _fact(
                    "external_reference_diameter",
                    token["value"],
                    label="Справочный / промежуточный наружный Ø",
                    source=token["source"],
                    confidence="medium",
                    note="Близок к основному наружному Ø; не считать осевым отверстием.",
                )
            )
            _mark(classified, token)
            continue
        if not any(
            item.get("type") in {"main_axial_hole", "main_axial_hole_candidate"}
            for item in features["internal_system"]
        ):
            features["internal_system"].append(
                _fact(
                    "main_axial_hole",
                    token["value"],
                    label="Основное осевое отверстие",
                    source=token["source"],
                    confidence="medium",
                    note="Ø без посадки; при наличии допуска +0,1 на чертеже указывай его явно.",
                )
            )
            _mark(classified, token)
        else:
            features["internal_system"].append(
                _fact(
                    "counterbore_or_stepped_hole",
                    token["value"],
                    label="Внутренняя ступень/расточка",
                    source=token["source"],
                    confidence="low",
                )
            )
            _mark(classified, token)


def _classify_threads(
    features: dict[str, Any],
    available: list[dict[str, Any]],
    classified: set[str],
) -> None:
    threads = [token for token in available if THREAD_RE.search(token.get("normalized", ""))]
    if not threads:
        return
    if not any(item.get("type") == "thread" for item in features["special_elements"]):
        features["special_elements"].append(
            _fact(
                "thread",
                [token["value"] for token in threads[:6]],
                label="Резьба",
                source=threads[0]["source"],
                confidence="high",
            )
        )
    _mark(classified, *threads)


def _parse_length_value(normalized: str) -> float | None:
    token = normalized.replace(" ", "")
    match = re.match(r"^L-?(\d+(?:,\d+)?)", token, re.IGNORECASE)
    if match:
        return float(match.group(1).replace(",", "."))
    match = re.match(r"^(\d+(?:,\d+)?)(?:±|\+|-)", token)
    if match:
        return float(match.group(1).replace(",", "."))
    return None


def _classify_lengths(
    features: dict[str, Any],
    available: list[dict[str, Any]],
    classified: set[str],
    text_evidence: list[str],
) -> None:
    length_tokens = [
        token
        for token in available
        if _is_length_token(token.get("normalized", ""))
    ]
    scored = [(token, _parse_length_value(token["normalized"])) for token in length_tokens]
    scored = [(token, value) for token, value in scored if value is not None]

    # Голые числа вроде «28» / «80» / «110» как габарит, если явная длина подозрительно мала.
    bare_lengths: list[tuple[float, str]] = []
    for item in text_evidence:
        token = item.strip().replace(",", ".")
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            value = float(token)
            if 15 <= value <= 400:
                bare_lengths.append((value, item.strip()))

    main_value = max((value for _, value in scored), default=None)
    outer_d = 0.0
    for fact in features.get("external_contour", []):
        if fact.get("type") == "outer_diameter":
            outer_d = _parse_diameter_mm(str(fact.get("value", "")))
            break

    if bare_lengths and (main_value is None or (outer_d and main_value < outer_d * 0.2)):
        candidates = bare_lengths
        # Для «дисковых» деталей (прижим/прокладка) высота обычно << наружного Ø.
        if outer_d >= 40:
            disk_like = [item for item in bare_lengths if item[0] <= outer_d * 0.5]
            if disk_like:
                candidates = disk_like
        bare_best = max(candidates, key=lambda item: item[0])
        if main_value is None or bare_best[0] > main_value * 1.5:
            features["overall"]["main_length"] = bare_best[1]
            features["external_contour"].append(
                _fact(
                    "overall_length",
                    bare_best[1],
                    label="Габаритная длина / высота",
                    source={"type": "text", "raw": bare_best[1]},
                    confidence="medium",
                    note="Взято из таблицы/текста как наибольшая правдоподобная длина.",
                )
            )

    if scored:
        main = max(scored, key=lambda item: item[1])[0]
        if "main_length" not in features["overall"]:
            features["overall"]["main_length"] = main["value"]
        # Длина относится к наружному контуру.
        if not any(item.get("type") == "overall_length" for item in features["external_contour"]):
            features["external_contour"].append(
                _fact(
                    "overall_length",
                    main["value"],
                    label="Габаритная длина",
                    source=main["source"],
                    confidence="medium",
                )
            )
        for token in length_tokens:
            _mark(classified, token)
    elif length_tokens:
        for token in length_tokens:
            _mark(classified, token)


def _classify_letter_parameters(
    features: dict[str, Any],
    available: list[dict[str, Any]],
    classified: set[str],
    text_evidence: list[str],
) -> None:
    for token in available:
        normalized = token.get("normalized", "")
        if re.match(r"^b-?\d", normalized, re.IGNORECASE):
            features["external_contour"].append(
                _fact(
                    "straight_section",
                    token["value"],
                    label="Прямой участок b",
                    source=token["source"],
                    confidence="medium",
                    note="Параметр b из таблицы/размера; указать по исполнениям.",
                )
            )
            features.setdefault("gdt", []).append(
                _fact(
                    "coaxiality_hint",
                    {"feature": token["value"], "base_hint": "A", "tolerance_mm_hint": "0,1"},
                    label="Соосность участка b относительно базы А",
                    source=token["source"],
                    confidence="low",
                    note="Если на чертеже есть допуск соосности для b — формулируй как отклонение от соосности плоскостей b относительно базы А (Ø наружный), не как биение отверстия.",
                )
            )
            _mark(classified, token)

    for item in text_evidence:
        if re.fullmatch(r"b-0[,.]2", item.strip(), re.IGNORECASE):
            if not any(fact.get("type") == "straight_section" for fact in features["external_contour"]):
                features["external_contour"].append(
                    _fact(
                        "straight_section",
                        item.strip(),
                        label="Прямой участок b",
                        source={"type": "text", "raw": item},
                        confidence="medium",
                    )
                )


def _classify_window_and_corner_holes(
    features: dict[str, Any],
    available: list[dict[str, Any]],
    classified: set[str],
    text_evidence: list[str],
) -> None:
    has_window = any(re.fullmatch(r"[hB]\+0[,.]1", item.strip(), re.IGNORECASE) for item in text_evidence)
    if not has_window:
        return

    features["internal_system"].append(
        _fact(
            "rectangular_window",
            {
                "parameters": ["h+0,1", "B+0,1"],
                "note": "Прямоугольное окно по таблице исполнений",
            },
            label="Прямоугольное внутреннее окно",
            source={"type": "text", "raw": "h+0,1 / B+0,1"},
            confidence="high",
            note="Опиши окно h/B по таблице; R в углах и фаски торца относи к окну.",
        )
    )
    features["llm_interpretation_rules"].append(
        "При наличии h+0,1/B+0,1 внутренняя система — прямоугольное окно, а не осевое круглое отверстие."
    )

    # Мелкие Ø8,5 с 90° — угловые глухие отверстия (спецэлементы), не основное отверстие.
    small_holes = [
        token
        for token in available
        if _is_diameter_token(token) and 6 <= _parse_diameter_mm(token["normalized"]) <= 12
    ]
    if small_holes:
        # Убрать ошибочно назначенное основное отверстие, если это мелкий Ø.
        features["internal_system"] = [
            fact
            for fact in features["internal_system"]
            if not (
                fact.get("type") in {"main_axial_hole", "main_axial_hole_candidate", "counterbore_or_stepped_hole"}
                and _parse_diameter_mm(str(fact.get("value", ""))) <= 12
            )
        ]
        features["special_elements"].append(
            _fact(
                "corner_blind_holes",
                {
                    "diameter": small_holes[0]["value"],
                    "quantity_hint": 2,
                    "angle": "90°",
                },
                label="Угловые глухие отверстия",
                source=small_holes[0]["source"],
                confidence="medium",
                note="2 глухих угловых отверстия; расстояние от торца буртика уточни по чертежу.",
            )
        )
        _mark(classified, *small_holes[:2])


def _classify_cone_angles(
    features: dict[str, Any],
    available: list[dict[str, Any]],
    classified: set[str],
    text_evidence: list[str],
) -> None:
    angles = [
        token
        for token in available
        if CONE_ANGLE_RE.match(token.get("normalized", "").replace(" ", ""))
        or re.search(r"^\d+(?:,\d+)?°", token.get("normalized", ""))
    ]
    if not angles:
        return
    # Углы 45° относятся к фаскам — не конус.
    cone_angles = [
        token
        for token in angles
        if not re.match(r"^45°", token.get("normalized", "").replace(" ", ""))
    ]
    if not cone_angles:
        return
    for token in cone_angles[:4]:
        if token["normalized"].lower() in classified:
            continue
        angle = _parse_angle_deg(token["normalized"])
        has_outer_var = any(re.fullmatch(r"D\*", item.strip(), re.I) for item in text_evidence)
        has_inner_var = any(re.fullmatch(r"d1\*", item.strip(), re.I) for item in text_evidence)
        if angle >= 80:
            target = "internal_system"
            label = "Конусный заход отверстия"
        elif has_outer_var and has_inner_var and angle <= 6.5:
            target = "internal_system"
            label = "Угол конуса отверстия"
        else:
            target = "external_contour"
            label = "Угол конуса наружной поверхности"
        note = "Привязка к наружной/внутренней поверхности по соседним размерам чертежа."
        fact = _fact("cone_angle", token["value"], label=label, source=token["source"], confidence="medium", note=note)
        features[target].append(fact)
        _mark(classified, token)


def _parse_angle_deg(normalized: str) -> float:
    match = re.match(r"^(\d+(?:,\d+)?)", normalized.replace(" ", ""))
    if not match:
        return 0.0
    return float(match.group(1).replace(",", "."))


def _classify_fillets(
    features: dict[str, Any],
    available: list[dict[str, Any]],
    classified: set[str],
) -> None:
    fillets = [
        token
        for token in available
        if re.match(r"^R\d+(?:,\d+)?$", token.get("normalized", ""), re.IGNORECASE)
    ]
    if not fillets:
        return
    outer_d = 0.0
    for fact in features.get("external_contour", []):
        if fact.get("type") == "outer_diameter":
            outer_d = _parse_diameter_mm(str(fact.get("value", "")))
            break

    for token in fillets[:6]:
        if token["normalized"].lower() in classified:
            continue
        radius = float(re.sub(r"[^\d,]", "", token["normalized"]).replace(",", ".") or "0")
        # Мусор размерных блоков: R34/R52 на детали Ø45…80.
        if radius >= 12 and (not outer_d or radius >= outer_d * 0.25):
            _mark(classified, token)
            continue
        if radius >= 4:
            features["external_contour"].append(
                _fact(
                    "fillet_or_blend",
                    token["value"],
                    label="Галтель / скругление наружного контура",
                    source=token["source"],
                    confidence="medium",
                )
            )
        elif features["internal_system"]:
            features["internal_system"].append(
                _fact(
                    "fillet_or_blend",
                    token["value"],
                    label="Скругление / плавный переход",
                    source=token["source"],
                    confidence="medium",
                )
            )
        else:
            features["external_contour"].append(
                _fact(
                    "fillet_or_blend",
                    token["value"],
                    label="Скругление",
                    source=token["source"],
                    confidence="low",
                )
            )
        _mark(classified, token)


def _classify_chamfers_generic(
    features: dict[str, Any],
    available: list[dict[str, Any]],
    classified: set[str],
) -> None:
    chamfers = [
        token
        for token in available
        if re.search(r"^\d+(?:[,.]\d+)?\s*[xх×]\s*\d+\s*°", token["normalized"], re.IGNORECASE)
    ]
    if not chamfers:
        return
    values = [token["value"] for token in chamfers[:8]]
    # Крупная фаска 6×45° на прижимах/окнах чаще внутренняя.
    large_internal = any(
        re.match(r"^[6-9](?:[,.]\d+)?×45", token["normalized"].replace(" ", ""), re.IGNORECASE)
        for token in chamfers
    )
    target = "internal_system" if large_internal else "external_contour"
    label = "Фаски внутренней системы" if large_internal else "Фаски наружного контура"
    features[target].append(
        _fact(
            "chamfers",
            values,
            label=label,
            source=chamfers[0]["source"],
            confidence="medium",
            note=(
                "Укажи количество (часто 2 на торцах) и принадлежность к Ø; "
                "не выноси в спецэлементы без отдельной группы отверстий/пазов."
            ),
        )
    )
    _mark(classified, *chamfers)
