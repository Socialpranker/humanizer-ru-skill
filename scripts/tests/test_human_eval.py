import json
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import human_eval as H  # noqa: E402

SYL = "ба ве го ду жи за ке ло му ни по ру са ти фу хо ци ча ши щу".split()


def word(rnd, lo=2, hi=4):
    return "".join(rnd.choice(SYL) for _ in range(rnd.randint(lo, hi)))


def text(seed, lengths):
    """Текст из выдуманных слов: у каждого зерна своя лексика, длины предложений заданы."""
    rnd = random.Random(seed)
    vocab = [word(rnd) for _ in range(60)]
    out = []
    for n in lengths:
        ws = [rnd.choice(vocab) for _ in range(n)]
        out.append(ws[0].capitalize() + " " + " ".join(ws[1:]) + ".")
    return " ".join(out)


def uneven(seed):
    rnd = random.Random(seed)
    return text(seed, [rnd.choice([3, 5, 8, 14, 22, 30]) for _ in range(12)])


def even(seed):
    return text(seed, [12] * 12)


class Features(unittest.TestCase):
    def test_short_text_has_no_features(self):
        self.assertIsNone(H.features("Коротко. Очень коротко."))

    def test_all_declared_features_are_measured(self):
        f = H.features(uneven(1))
        self.assertEqual(set(f), set(H.FEATURES))
        self.assertNotIn("dash", f)

    def test_even_sentences_have_low_spread(self):
        self.assertLess(H.features(even(1))["sent_cv"], 0.05)
        self.assertGreater(H.features(uneven(1))["sent_cv"], 0.4)


class Plain(unittest.TestCase):
    def test_strips_markup_and_title_line(self):
        t = H.plain("Итоги года: что вышло\n\n# Раздел\n\n- **Первый** пункт был готов.\n\nВторой абзац идёт следом.")
        self.assertEqual(t, "Первый пункт был готов. Второй абзац идёт следом.")

    def test_cuts_at_sentence_boundary(self):
        t = H.plain(text(2, [10, 10, 10, 10]), 25)
        self.assertEqual(len(H.W.findall(t)), 20)
        self.assertTrue(t.endswith("."))


class Topic(unittest.TestCase):
    def test_same_and_different_topics(self):
        a = H.topic(text(3, [12] * 10))
        self.assertTrue(H.same_topic(a, H.topic(text(3, [9] * 12))))
        self.assertFalse(H.same_topic(a, H.topic(text(4, [12] * 10))))


class Auroc(unittest.TestCase):
    def test_auroc(self):
        self.assertEqual(H.auroc([2, 3], [0, 1]), 1.0)
        self.assertEqual(H.auroc([0, 1], [2, 3]), 0.0)
        self.assertEqual(H.auroc([1, 1], [1, 1]), 0.5)


class Profile(unittest.TestCase):
    def test_even_text_falls_out_of_human_range(self):
        human = [(str(i), uneven(100 + i)) for i in range(30)]
        r = H.profile([("x", even(7))], human)
        out = {x["key"] for x in r["rows"] if x["out"]}
        self.assertIn("sent_cv", out)
        self.assertIn("ниже, чем у людей", H.profile_report(r))

    def test_set_is_compared_pairwise(self):
        human = [(str(i), uneven(100 + i)) for i in range(30)]
        rep = H.profile_report(H.profile([(str(i), even(600 + i)) for i in range(10)], human))
        self.assertRegex(rep, r"разброс длины предложений[^\n]*ниже, чем у людей, в 100% пар")

    def test_human_like_text_stays_inside(self):
        human = [(str(i), uneven(100 + i)) for i in range(30)]
        r = H.profile([(str(i), uneven(500 + i)) for i in range(12)], human)
        self.assertEqual([x["key"] for x in r["rows"] if x["out"]], [])

    def test_even_paragraphs_fall_out_of_human_range(self):
        def paras(seed, sizes):
            return "\n\n".join(text(seed * 100 + i, [10] * k) for i, k in enumerate(sizes))

        rnd = random.Random(5)
        human = [(str(i), paras(100 + i, [rnd.choice([1, 2, 3, 6]) for _ in range(6)])) for i in range(40)]
        r = H.profile([(str(i), paras(600 + i, [3] * 6)) for i in range(10)], human)
        self.assertIn("par_cv", {x["key"] for x in r["rows"] if x["out"]})
        self.assertRegex(H.profile_report(r), r"разброс длины абзацев[^\n]*ниже, чем у людей")
        like = H.profile([(str(i), paras(700 + i, [rnd.choice([1, 2, 3, 6]) for _ in range(6)])) for i in range(10)], human)
        self.assertNotIn("par_cv", {x["key"] for x in like["rows"] if x["out"]})

    def test_paragraphs_skipped_without_line_breaks(self):
        human = [(str(i), uneven(100 + i)) for i in range(30)]
        r = H.profile([("x", even(7))], human)
        self.assertNotIn("par_cv", {x["key"] for x in r["rows"]})
        self.assertIn("Абзацы не сравнивались", H.profile_report(r))

    def test_headings_and_list_items_are_not_paragraphs(self):
        t = "# Раздел\n\nПервый абзац из пяти слов.\n\n- пункт списка\n- ещё пункт\n\nВторой абзац.\n\nТретий абзац чуть длиннее второго."
        f = H.par_features(t)
        self.assertAlmostEqual(f["par_per100"], 100.0 * 3 / 12)
        self.assertIsNone(H.par_features("Один абзац.\n\nВторой абзац."))

    def test_small_reference_is_refused(self):
        r = H.profile([("x", even(7))], [(str(i), uneven(i)) for i in range(5)])
        self.assertIn("error", r)
        self.assertIn("Сравнить не с чем", H.profile_report(r))


class PackAndScore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        for kind, n, make in (("human", 14, uneven), ("control", 8, even), ("cand", 6, uneven)):
            os.makedirs(os.path.join(d, kind))
            for i in range(n):
                seed = {"human": 200, "control": 300, "cand": 400}[kind] + i
                H._write(os.path.join(d, kind, f"{i:02d}.txt"), make(seed))
        # тот же текст второй раз под другим именем: в пачку должна попасть одна копия
        H._write(os.path.join(d, "cand", "copy.txt"), uneven(400))
        self.out = os.path.join(d, "pack")
        self.key = H.pack(self.out, [os.path.join(d, "human", "*.txt")], [os.path.join(d, "control", "*.txt")], [("набор", os.path.join(d, "cand", "*.txt"))], per=6, words=120, seed=5)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pack_is_blind_and_has_one_copy_per_topic(self):
        kinds = [k["kind"] for k in self.key.values()]
        self.assertEqual((kinds.count("candidate"), kinds.count("control"), kinds.count("human")), (6, 6, 6))
        srcs = [k["src"] for k in self.key.values() if k["kind"] == "candidate"]
        self.assertFalse({"00.txt", "copy.txt"} <= {os.path.basename(s) for s in srcs})
        body = str(H.S.read(os.path.join(self.out, "pack.text")))
        self.assertNotIn(self.tmp.name, body)
        self.assertNotIn("набор", body)
        self.assertIn("verdict_ИМЯ.json", str(H.S.read(os.path.join(self.out, "brief.text"))))

    def _verdict(self, name, p_by_kind):
        path = os.path.join(self.out, name)
        H._write(path, json.dumps({t: {"p": p_by_kind[k["kind"]], "cue": "слова"} for t, k in self.key.items()}))
        return path

    def test_score_with_working_judge(self):
        v = self._verdict("v1.json", {"human": 10, "control": 90, "candidate": 10})
        r = H.score(self.out, [v])
        self.assertEqual(r["power"], 1.0)
        self.assertEqual(r["fpr"], 0.0)
        cand = [s for s in r["sets"] if s["kind"] == "candidate"][0]
        self.assertEqual((cand["flagged"], cand["auroc"]), (0.0, 0.5))
        self.assertIn("Судья набор от людей не отличил", H.score_report(r))

    def test_score_reports_residual_suspicion(self):
        v = self._verdict("v4.json", {"human": 10, "control": 90, "candidate": 30})
        rep = H.score_report(H.score(self.out, [v]))
        self.assertIn("остаточные приметы есть", rep)
        self.assertNotIn("Судья отличает набор", rep)

    def test_score_flags_detected_set(self):
        v = self._verdict("v2.json", {"human": 10, "control": 90, "candidate": 80})
        rep = H.score_report(H.score(self.out, [v]))
        self.assertIn("Судья отличает набор от людей", rep)
        self.assertIn("слова", rep)

    def test_blind_judge_fails_control(self):
        v = self._verdict("v3.json", {"human": 50, "control": 50, "candidate": 50})
        rep = H.score_report(H.score(self.out, [v]))
        self.assertIn("Контроль не пройден", rep)
        self.assertNotIn("не отличил", rep)


if __name__ == "__main__":
    unittest.main()
