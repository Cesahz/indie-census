#suite de calibracion de precision y exhaustividad de clasificadores
#evalua cumplimiento de precision >= 0.95 en evidencia niveles 1 y 2
from typing import Any

from src.classify.ai import NivelDivulgacionIA, clasificar_divulgacion_ia
from src.classify.engine import clasificar_motor
from src.classify.indie import calcular_indie_score
from src.classify.taxonomy import cargar_taxonomia

#muestra anotada con verdad de terreno (ground truth) curada manualmente
MUESTRA_ANOTADA_MOTORES: list[dict[str, Any]] = [
    #nivel 1: declaracion formal
    {
        "descripcion": "An atmospheric action roguelike proudly made with Godot.",
        "creditos": None,
        "tags": ["Action", "Roguelike"],
        "motor_esperado": "godot",
        "nivel_esperado": 1,
    },
    {
        "descripcion": "Explore mysterious caverns. Built with Unreal Engine 5.",
        "creditos": None,
        "tags": ["Adventure", "3D"],
        "motor_esperado": "unreal",
        "nivel_esperado": 1,
    },
    {
        "descripcion": "Retro platformer.",
        "creditos": "Created with GameMaker Studio by SoloDev.",
        "tags": ["Platformer", "2D"],
        "motor_esperado": "gamemaker",
        "nivel_esperado": 1,
    },
    {
        "descripcion": "Puzzle game powered by Unity.",
        "creditos": None,
        "tags": ["Puzzle"],
        "motor_esperado": "unity",
        "nivel_esperado": 1,
    },
    {
        "descripcion": "Juego de rol desarrollado con Godot por un equipo indie.",
        "creditos": None,
        "tags": ["RPG"],
        "motor_esperado": "godot",
        "nivel_esperado": 1,
    },
    #nivel 2: tags de tienda
    {
        "descripcion": "A fast-paced multiplayer arena shooter.",
        "creditos": None,
        "tags": ["Shooter", "godot", "Indie"],
        "motor_esperado": "godot",
        "nivel_esperado": 2,
    },
    {
        "descripcion": "Procedural survival game with realistic physics.",
        "creditos": None,
        "tags": ["Survival", "unity", "Open World"],
        "motor_esperado": "unity",
        "nivel_esperado": 2,
    },
    {
        "descripcion": "High-fidelity racing simulator.",
        "creditos": None,
        "tags": ["Racing", "unreal engine"],
        "motor_esperado": "unreal",
        "nivel_esperado": 2,
    },
    {
        "descripcion": "Pixel art metroidvania adventure.",
        "creditos": None,
        "tags": ["Metroidvania", "gamemaker", "Pixel Graphics"],
        "motor_esperado": "gamemaker",
        "nivel_esperado": 2,
    },
    {
        "descripcion": "Cute puzzle mechanics with cards.",
        "creditos": None,
        "tags": ["Puzzle", "godot", "Card Game"],
        "motor_esperado": "godot",
        "nivel_esperado": 2,
    },
    #nivel 4: mencion regex en texto sin declaracion formal
    {
        "descripcion": "Our team moved away from older engines to explore godot tools.",
        "creditos": None,
        "tags": ["Indie"],
        "motor_esperado": "godot",
        "nivel_esperado": 4,
    },
    {
        "descripcion": "Custom scripts built on unity3d architecture.",
        "creditos": None,
        "tags": ["Strategy"],
        "motor_esperado": "unity",
        "nivel_esperado": 4,
    },
    #casos negativos / sin motor
    {
        "descripcion": "A cozy farming simulator in a magical village.",
        "creditos": None,
        "tags": ["Farming Sim", "Casual", "Cozy"],
        "motor_esperado": "unknown",
        "nivel_esperado": None,
    },
    {
        "descripcion": "Classic chess puzzles with historical themes.",
        "creditos": None,
        "tags": ["Chess", "Board Game"],
        "motor_esperado": "unknown",
        "nivel_esperado": None,
    },
    {
        "descripcion": "Space exploration and resource management.",
        "creditos": None,
        "tags": ["Sci-Fi", "Space", "Simulation"],
        "motor_esperado": "unknown",
        "nivel_esperado": None,
    },
]


def test_precision_exhaustividad_motor_niveles_1_y_2() -> None:
    """Certificar que la precision del clasificador de motor es >= 0.95 en niveles 1 y 2."""
    tax = cargar_taxonomia()

    verdaderos_positivos = 0
    falsos_positivos = 0
    falsos_negativos = 0

    for caso in MUESTRA_ANOTADA_MOTORES:
        res = clasificar_motor(
            descripcion=caso["descripcion"],
            creditos=caso["creditos"],
            tags=caso["tags"],
            taxonomia=tax,
        )

        espera_nivel_alto = caso["nivel_esperado"] in (1, 2)
        predijo_nivel_alto = res.evidence_level in (1, 2)

        if predijo_nivel_alto:
            if espera_nivel_alto and res.engine == caso["motor_esperado"]:
                verdaderos_positivos += 1
            else:
                falsos_positivos += 1
        elif espera_nivel_alto:
            falsos_negativos += 1

    total_predichos = verdaderos_positivos + falsos_positivos
    assert total_predichos > 0, "No se emitieron predicciones para niveles 1 y 2"
    precision = verdaderos_positivos / total_predichos

    total_relevantes = verdaderos_positivos + falsos_negativos
    assert total_relevantes > 0, "No se encontraron casos relevantes anotados"
    exhaustividad = verdaderos_positivos / total_relevantes

    #criterio f2-05: precision minima de 0.95 para niveles 1-2
    assert precision >= 0.95, f"Precision insuficiente: {precision:.4f} < 0.95"
    assert exhaustividad >= 0.85, f"Exhaustividad insuficiente: {exhaustividad:.4f} < 0.85"


def test_calibracion_indie_score_separacion_clara() -> None:
    """Verificar que el indie_score separa claramente juegos indie de AAA."""
    tax = cargar_taxonomia()

    indies = [
        {"tags": ["Indie"], "devs": ["Dev A"], "pubs": ["Dev A"], "price": 9.99, "langs": 1},
        {"tags": ["Indie", "Action"], "devs": ["Studio X"], "pubs": ["Studio X"], "price": 19.99, "langs": 3},
        {"tags": ["Indie", "Puzzle"], "devs": ["Solo"], "pubs": [], "price": 0.0, "langs": 1},
    ]

    aaas = [
        {"tags": ["Action"], "devs": ["EA Vancouver"], "pubs": ["Electronic Arts"], "price": 69.99, "langs": 12},
        {"tags": ["Open World"], "devs": ["Ubisoft Paris"], "pubs": ["Ubisoft"], "price": 59.99, "langs": 15},
        {"tags": ["Sports"], "devs": ["Visual Concepts"], "pubs": ["2K"], "price": 69.99, "langs": 10},
    ]

    scores_indies = [
        calcular_indie_score(
            tags=i["tags"],
            developers=i["devs"],
            publishers=i["pubs"],
            price_usd=i["price"],
            language_count=i["langs"],
            taxonomia=tax,
        ).indie_score
        for i in indies
    ]

    scores_aaas = [
        calcular_indie_score(
            tags=a["tags"],
            developers=a["devs"],
            publishers=a["pubs"],
            price_usd=a["price"],
            language_count=a["langs"],
            taxonomia=tax,
        ).indie_score
        for a in aaas
    ]

    #cada juego indie debe superar holgadamente a cada juego aaa
    assert min(scores_indies) >= 0.70
    assert max(scores_aaas) <= 0.25
    assert min(scores_indies) > max(scores_aaas) + 0.40


def test_calibracion_ia_consistencia() -> None:
    """Verificar coherencia de clasificacion de IA sobre patrones conocidos."""
    tax = cargar_taxonomia()

    casos_ia = [
        (["generative ai used in backgrounds"], [], None, NivelDivulgacionIA.DECLARED),
        ([], ["generative ai"], None, NivelDivulgacionIA.TAGGED),
        ([], [], "voces generadas por ia para dialogos secundarios", NivelDivulgacionIA.SELF_REPORTED),
        ([], ["hand-drawn", "cozy"], "handcrafted game", NivelDivulgacionIA.UNKNOWN),
    ]

    for desc_steam, tags, notas, esperado in casos_ia:
        res = clasificar_divulgacion_ia(
            descriptors_steam=desc_steam,
            tags=tags,
            descripcion_o_notas=notas,
            taxonomia=tax,
        )
        assert res.disclosure_level == esperado
