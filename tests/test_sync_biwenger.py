import unittest

from sync_biwenger import (
    board_rounds,
    is_mirrored_prematch,
    rank_results,
    set_round,
)


class SyncBiwengerTests(unittest.TestCase):
    def test_board_rounds_keeps_dates_and_final_results(self):
        board = [
            {
                "type": "roundStarted",
                "date": 100,
                "content": {"round": {"id": 4900, "name": "Jornada 2"}},
            },
            {"type": "market", "content": []},
            {
                "type": "roundFinished",
                "date": 200,
                "content": {
                    "round": {"id": 4899, "name": "Jornada 1"},
                    "results": [{"user": {"name": "A"}, "points": 10}],
                },
            },
        ]

        rounds = board_rounds(board)

        self.assertEqual(rounds[4900]["number"], 2)
        self.assertEqual(rounds[4900]["started_at"], 100)
        self.assertFalse(rounds[4900]["finished"])
        self.assertEqual(rounds[4899]["finished_at"], 200)
        self.assertTrue(rounds[4899]["finished"])
        self.assertEqual(rounds[4899]["results"][0]["points"], 10)

    def test_rank_results_preserves_api_order_for_ties_and_bonus(self):
        results = [
            {"user": {"name": "A"}, "points": 35, "bonus": 1_750_000},
            {"user": {"name": "B"}, "points": 35, "bonus": 2_000_000},
            {"user": {"name": "C"}, "points": 20, "bonus": 1_000_000},
        ]

        ranked = rank_results(results)

        self.assertEqual([row["name"] for row in ranked], ["A", "B", "C"])
        self.assertEqual([row["position"] for row in ranked], [1, 2, 3])
        self.assertEqual(ranked[1]["bonus"], 2_000_000)

    def test_last_positions_can_replace_inferred_position_without_losing_bonus(self):
        player = {"positions": {}, "rounds": {}}
        set_round(player, 1, 2, "final", 35, bonus=2_000_000, round_id=4899)
        existing = player["rounds"]["1"]

        set_round(
            player,
            1,
            1,
            "final",
            existing["points"],
            bonus=existing["bonus"],
            round_id=existing["round_id"],
        )

        self.assertEqual(player["positions"]["1"], 1)
        self.assertEqual(player["rounds"]["1"]["bonus"], 2_000_000)

    def test_mirrored_live_round_is_prematch(self):
        players = {
            "A": {
                "rounds": {"1": {"status": "final", "points": 35}},
            },
            "B": {
                "rounds": {"1": {"status": "final", "points": 20}},
            },
        }

        self.assertTrue(
            is_mirrored_prematch(
                [("A", 1, 35), ("B", 2, 20)], players, 1, {1}
            )
        )
        self.assertFalse(
            is_mirrored_prematch(
                [("A", 1, 36), ("B", 2, 20)], players, 1, {1}
            )
        )


if __name__ == "__main__":
    unittest.main()
