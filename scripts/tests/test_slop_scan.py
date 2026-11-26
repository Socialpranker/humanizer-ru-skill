"""Регрессия сканера: python3 -m unittest discover -s ~/.claude/skills/humanizer-ru/scripts/tests"""

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import slop_scan as S  # noqa: E402

BAD = (
    "В современном бизнес-ландшафте автоматизация играет ключевую роль. Данное исследование "
    "рассматривает подход, позволяющий осуществлять управление. Несмотря на многочисленные вызовы, "
    "организации идут вперёд. Это не просто инструмент — это новый способ мышления. "
    "Эксперты считают, что подход открывает новые горизонты.\n\nОтличный вопрос! Надеюсь, это поможет."
)
GOOD = (
    "Компании автоматизируют рутину, потому что это дешевле. Мы прогнали 40 проектов за два года "
    "и нашли четыре типовые ошибки. Большинство проектов буксуют не из-за технологий."
)
MASKED = "Обычный текст.\n\n```\nосуществляет контроль, является, в рамках\n```\n\n> Эксперты считают, что это не просто X, а Y.\n"


class ScannerTests(unittest.TestCase):
    def test_bad_text_fires_and_clusters(self):
        r = S.scan(BAD)
        self.assertGreaterEqual(len(r["markers"]), 8)
        self.assertEqual(len(r["clusters"]), 1)
        self.assertLess(r["score"], 50)

    def test_good_text_is_silent(self):
        r = S.scan(GOOD)
        self.assertEqual(r["markers"], [])
        self.assertGreater(r["score"], 90)

    def test_code_and_quotes_are_masked(self):
        self.assertEqual(S.scan(MASKED)["markers"], [])

    def test_marker_outside_mask_still_fires(self):
        self.assertEqual(
            len(S.scan("Программа является частью проекта.\n" + MASKED)["markers"]), 1
        )

    def test_genre_mutes_legal(self):
        legal = "Является предметом договора в рамках данного соглашения, в целях исполнения."
        self.assertGreater(len(S.scan(legal)["markers"]), 0)
        self.assertEqual(S.scan(legal, "legal")["markers"], [])

    def test_genre_mutes_science(self):
        sci = "Статья посвящена анализу рынка. Ряд источников указывают на схожий результат."
        self.assertGreater(len(S.scan(sci)["markers"]), 0)
        self.assertEqual(S.scan(sci, "science")["markers"], [])

    def test_genre_mutes_business_and_news(self):
        biz = "В связи с этим было принято решение о пересмотре бюджета на следующий квартал."
        self.assertGreater(len(S.scan(biz)["markers"]), 0)
        self.assertEqual(S.scan(biz, "business")["markers"], [])
        self.assertEqual(S.scan(biz, "news")["markers"], [])

    def test_juzek_lemmas_fire_and_neutral_is_silent(self):
        slop = "Доклад подчёркивает центральную роль партнёрства, что имеет первостепенную важность для отрасли."
        self.assertGreaterEqual(len(S.scan(slop)["markers"]), 2)
        neutral = "Редактор подчёркивает опечатки красным маркером. Важность решения обсудили на встрече."
        self.assertEqual(S.scan(neutral)["markers"], [])

    def test_fact_check_catches_losses(self):
        before = "Ромашка в 2019 году выросла на 12,5%. Директор Иванов доволен."
        self.assertEqual(S.fact_check(before, before), [])
        lost = " ".join(S.fact_check(before, "Компания выросла."))
        self.assertIn("12.5%", lost)
        self.assertIn("2019", lost)

    def test_dropped_dashes_found_against_source(self):
        before = "ОАО НИС — лидер рынка. ОАО «МТС-Банк» — универсальный банк. Слева — эскиз, справа — оригинал. Учителям — по шесть тысяч."
        self.assertEqual(
            S.dropped_dashes(before, "НИС лидер рынка, а «МТС-Банк» универсальный банк."),
            ["НИС лидер", "Банк» универсальный"],
        )
        rebuilt = "НИС лидирует на рынке. МТС-Банк работает как универсальный банк. Слева эскиз, справа оригинал. Учителям по шесть тысяч."
        self.assertEqual(S.dropped_dashes(before, rebuilt), [])

    def test_every_marker_label_documented(self):
        # каталог и код не должны разъезжаться: метка дословно живёт в patterns.md (раздел «Метки сканера»)
        doc = (
            open(
                os.path.join(HERE, "..", "..", "references", "patterns.md"),
                encoding="utf-8",
            )
            .read()
            .lower()
        )
        missing = [label for _c, label, _rx in S.MARKERS if label.lower() not in doc]
        self.assertEqual(missing, [])

    def test_regexes_compile(self):
        for _c, label, rx in S.MARKERS:
            re.compile(rx, re.IGNORECASE)



class TestShortSentences(unittest.TestCase):
    LONG = "Команда перенесла расчёт отчётов на ночное время, потому что дневная нагрузка мешала продавцам работать. "
    SHORT = "Это помогло. "

    def test_flat_prose_flagged(self):
        r = S.scan(self.LONG * 14)
        self.assertTrue(any("нет коротких предложений" in f for f in r["flags"]))

    def test_mixed_rhythm_not_flagged(self):
        r = S.scan((self.LONG * 3 + self.SHORT) * 5)
        self.assertFalse(any("нет коротких предложений" in f for f in r["flags"]))

    def test_news_genre_muted(self):
        r = S.scan(self.LONG * 14, "news")
        self.assertFalse(any("нет коротких предложений" in f for f in r["flags"]))


class TestFragments(unittest.TestCase):
    OLD = (
        "все графы, указан способ приёма, анонс вышел до начала приёма заявок\n\n"
        "записи приходят в срок, формат не меняется от периода к периоду\n\n"
    )
    NEW = (
        "В записи заполнены все обязательные графы, и указано, как принимали заявки.\n\n"
        "Организация передаёт записи в срок и не меняет формат от периода к периоду.\n\n"
    )

    def test_telegraphic_fragments_flagged(self):
        r = S.scan(self.OLD * 3)
        self.assertTrue(any("обрубки" in f for f in r["flags"]))

    def test_full_sentences_not_flagged(self):
        r = S.scan(self.NEW * 3)
        self.assertFalse(any("обрубки" in f for f in r["flags"]))

    def test_abbreviations_flagged(self):
        r = S.scan("Колонка Мин показывает минимум, а колонка Опт показывает оптимальный ярус.")
        self.assertTrue(any("сокращения" in f for f in r["flags"]))

    def test_headings_and_tables_ignored(self):
        r = S.scan("# все графы, указан способ приёма, анонс\n| все графы, указан способ, анонс |\n")
        self.assertFalse(any("обрубки" in f for f in r["flags"]))


class TestCoherence(unittest.TestCase):
    # перечень фактов по образцу реального документа: соседние предложения ничем не сцеплены
    LIST_OF_FACTS = (
        "Для нового сервера в жидкостном исполнении нужна стойка до 40 киловатт. "
        "Ни один оператор в регионе пока не подтвердил параметры площадки. "
        "Шинопровод рассчитан на полную нагрузку зала. "
        "Ответы просим присылать письменно с подписью. "
        "Цены на электроэнергию указаны без налога. "
    )
    LINKED = (
        "Для нового сервера в жидкостном исполнении нужна стойка до 40 киловатт. "
        "Такую стойку в регионе пока не подтвердил ни один оператор. "
        "Поэтому мы просим каждого оператора ответить письменно. "
        "В ответе оператор указывает мощность стойки и тип охлаждения. "
        "Без этих двух цифр площадку не рассматриваем. "
    )

    def test_list_of_facts_flagged(self):
        r = S.scan((self.LIST_OF_FACTS + "\n\n") * 3)
        self.assertTrue(any(f.startswith("связность") for f in r["flags"]))

    def test_linked_prose_not_flagged(self):
        r = S.scan((self.LINKED + "\n\n") * 3)
        self.assertFalse(any(f.startswith("связность") for f in r["flags"]))

    def test_lists_are_not_prose(self):
        r = S.scan("\n".join("- " + s for s in self.LIST_OF_FACTS.split(". ")) * 3)
        self.assertFalse(any(f.startswith("связность") for f in r["flags"]))

    def test_verbless_sentences_flagged(self):
        labels = "Стойка жидкостная на сто киловатт. Ввод 480 вольт трёхфазный. Охлаждение прямое жидкостное с теплообменником. "
        r = S.scan((labels + "\n\n") * 4)
        self.assertTrue(any("без сказуемого" in f for f in r["flags"]))
        self.assertFalse(any("без сказуемого" in f for f in S.scan((labels + "\n\n") * 4, "science")["flags"]))

    def test_verbal_sentences_not_flagged(self):
        r = S.scan((self.LINKED + "\n\n") * 3)
        self.assertFalse(any("без сказуемого" in f for f in r["flags"]))


class TestNewMarkers2026_10(unittest.TestCase):
    # положительный пример на каждую новую метку; контрпримеры — обычные фразы с теми же словами
    POS = {
        "«Это важно.» отдельной фразой": "Мы выбрали Postgres. Это важно. Дальше",
        "честный ответ / правда в том": "Честный ответ — да, но с оговорками.",
        "Вот в чём дело:": "Запрос тормозит. Вот в чём дело: индекс не используется.",
        "подвох в том": "Подвох в том, что кэш не сбрасывается.",
        "тихо меняет": "Инструмент тихо меняет процесс разработки.",
        "Спойлер:/Если коротко:": "Итог. Спойлер: он не сработал.",
        "Не потому что X. А потому что Y": "Не потому, что он слаб. А потому, что он дорог.",
        "решение рождается": "Постепенно решение рождается из обсуждения.",
        "служит напоминанием": "Этот случай служит напоминанием о рисках.",
        "деепричастный хвост: подчёркивая значимость": "Закон принят в 2020 году, подчёркивая значимость реформы.",
        "заголовок «Ключевые выводы»": "**Ключевые выводы:**",
        "зачин с двоеточием: Итог:/Вывод:": "Мы сравнили три базы. Итог: Postgres быстрее.",
        "ровно как усилитель": "Это ровно та ошибка, о которой писал автор."
    }
    NEG = [
        "Это важно для понимания закона сохранения.",
        "Он ответил честно.",
        "Вот список файлов в каталоге.",
        "Загвоздка не найдена.",
        "Простыми словами не объяснить.",
        "Поезд пришёл ровно в восемь.",
        "Итоговая сумма указана в таблице."
    ]

    def test_each_new_label_fires(self):
        for label, text in self.POS.items():
            with self.subTest(label=label):
                self.assertIn(label, {h["label"] for h in S.scan(text)["markers"]})

    def test_neutral_lookalikes_silent(self):
        for text in self.NEG:
            with self.subTest(text=text):
                self.assertEqual(S.scan(text)["markers"], [])

    def test_announcing_lead_ins(self):
        # формы из слепого чтения этапа 6: предложение обещает следующее и само ничего не сообщает
        label = "подводка-анонс: Причин две. / Вывод простой:"
        for text in (
            "Запуск переносится. Причин две. Тексты пришли позже.",
            "Запуск переносится на 15 декабря по двум причинам.",
            "Вывод для нас простой: интерес не равен покупке.",
            "Главный вопрос для вас такой: где лежат документы.",
            "Первый вопрос к команде звучит так: кто отвечает за базу.",
            "Инвестор обычно спрашивает про четыре вещи.",
            "Мы закрыли проект. Вот почему.",
            "Jolla основана в 2011 году. Теперь об инвесторах Jolla. Их трое.",
            "Компания повышает выпуск, и итог такой: она считает себя лидером.",
            "Итоги по десяти принятым такие. Один проект закрыт.",
            "Для тех, кто только начинает, из этого два вывода. Первый касается ниши.",
            "У такого постоянства я вижу три возможных объяснения. Одним подходит рутина.",
            "Чтобы начать работу, нужно пройти несколько простых шагов. Сначала регистрация.",
        ):
            with self.subTest(text=text):
                self.assertIn(label, {h["label"] for h in S.scan(text)["markers"]})
        for text in (
            "Причины задержки названы в письме от 3 декабря.",
            "Вопрос простой, и ответ на него есть в договоре.",
            "Вот почему мы перенесли запуск на 15 декабря.",
            "Мы купили три вещи: стол, лампу и кресло.",
            "Теперь о сроках мы узнаём из рассылки, а не из чата.",
            "Итог встречи записан в протоколе от 3 декабря.",
            "Линтер нашёл три ошибки. Две из них в тестах.",
            "За неделю закрыли пять задач. Осталась миграция.",
            "Меня занимают три вопроса: почему уходят, как удержать и нужно ли.",
        ):
            with self.subTest(text=text):
                self.assertNotIn(label, {h["label"] for h in S.scan(text)["markers"]})

    def test_retelling_seams(self):
        # приметы слепого судьи 22.11.2026: пересказ ссылается на оригинал или путает лицо говорящего
        label = "шов пересказа: в оригинале есть / по моим словам"
        for text in (
            "В оригинале есть график зависимости качества от числа фильтров.",
            "Корпорация, по моим словам, образец для многих предприятий.",
        ):
            with self.subTest(text=text):
                self.assertIn(label, {h["label"] for h in S.scan(text)["markers"]})
        for text in (
            "Фильм в оригинале называется иначе, и перевод потерял игру слов.",
            "По словам директора, корпорация служит образцом для многих.",
        ):
            with self.subTest(text=text):
                self.assertNotIn(label, {h["label"] for h in S.scan(text)["markers"]})

    def test_blader_2026_11_labels_fire(self):
        pos = {
            "спор с никем: не поймите неправильно": "Не поймите меня неправильно, документация нужна.",
            "текст о документе: таблица ниже сравнивает": "Таблица ниже сравнивает шесть вариантов.",
            "разгон: штука в том, что": "Кэш работает. Штука в том, что он не сбрасывается.",
            "афоризм: язык доверия / настоящий вопрос": "Симметрия — язык доверия.",
            "слова через точку: каждый. божий. день.": "Он пишет код каждый. божий. день.",
            "догадка на пустом месте: сведений нет в открытом доступе": "Сведения о её детстве не раскрываются.",
        }
        for label, text in pos.items():
            with self.subTest(label=label):
                self.assertIn(label, {h["label"] for h in S.scan(text)["markers"]})
        for text in ("Сразу оговорюсь, что тест синтетический.", "Полн. собр. соч. Т. 5.", "Общество. Среда. Развитие.",
                     "Напрашивается вывод о росте цен.", "Самое сложное позади, и мы выпустили релиз."):
            with self.subTest(text=text):
                self.assertEqual(S.scan(text)["markers"], [])

    def test_dashes_rare(self):
        two = "Москва — столица, а Киев — тоже столица. " + "Город растёт и строится. " * 10
        self.assertTrue(any(f.startswith("тире") for f in S.scan(two)["flags"]))
        one = "Москва — столица. " + "Город растёт и строится. " * 10
        # свой текст: и одно тире флаг; чужой на правке (foreign): одно на 200 слов проходит, два нет
        self.assertTrue(any(f.startswith("тире") for f in S.scan(one)["flags"]))
        self.assertFalse(any(f.startswith("тире") for f in S.scan(one, foreign=True)["flags"]))
        self.assertTrue(any(f.startswith("тире") for f in S.scan(two, foreign=True)["flags"]))
        self.assertFalse(any(f.startswith("тире") for f in S.scan("Город растёт и строится. " * 10)["flags"]))
        # реплика диалога, диапазон, пункт списка и пустая ячейка таблицы тире не считаются
        neutral = "— Привет, сказал он.\nЦена 5–10 рублей.\n- пункт списка\n| a | - |\n"
        self.assertEqual(len(S.DASH.findall(neutral)), 0)
        self.assertEqual(len(S.DASH.findall("слово - слово -- слово—слово")), 3)

    def test_mid_sentence_colon_limited(self):
        colon = lambda r: [f for f in r["flags"] if f.startswith("двоеточие в середине")]
        one = "Заняться версией я не могу: у меня ограничение по трафику. "
        filler = "Город растёт и строится. " * 10
        # свой текст: одно двоеточие в коротком тексте проходит, два нет; совет при тире двоеточие не предлагает
        self.assertEqual(colon(S.scan(one + filler)), [])
        two = one + "Рассылки вчера вечером стояли: письма копились и не уходили. " + filler
        self.assertEqual(len(colon(S.scan(two))), 1)
        self.assertNotIn("двоеточием,", [f for f in S.scan("Москва — столица. " + filler)["flags"] if f.startswith("тире")][0])
        # чужой текст на правке: одно на 100 слов, поэтому два двоеточия на 200 слов проходят, а три нет
        long = filler * 5
        self.assertEqual(colon(S.scan(two + long, foreign=True)), [])
        self.assertEqual(len(colon(S.scan(two + one + long, foreign=True))), 1)
        # ярлык в одно-два слова, время, заглавная после двоеточия и слайды в счёт не идут
        neutral = "Первый: ноутбук на 13 дюймов. Второй: ноутбук на 15 дюймов. Встреча в 12:30. Тема письма: План работ. "
        self.assertEqual(S.mid_colons(S.split_sentences(neutral)), [])
        self.assertEqual(colon(S.scan(two + filler, slides=[])), [])

    def test_reverse_antithesis_flagged_in_own_text(self):
        # решение автора 23.11.2026: любой «, а не» в своём тексте, в чужом на правке молчит
        text = "Дешевле начать с задачи, где ошибку заметит сотрудник, а не клиент."
        own = [h for h in S.scan(text)["markers"] if h["label"] == S.REVERSE_LABEL]
        self.assertEqual([h["text"] for h in own], ["сотрудник, а не клиент"])
        self.assertEqual(own[0]["cat"], "антитеза")
        self.assertNotIn(S.REVERSE_LABEL, {h["label"] for h in S.scan(text, foreign=True)["markers"]})
        for clean in ("Сотрудник заметит ошибку раньше клиента.", "Он написал «решает сотрудник, а не клиент» и ушёл.",
                      "А не пора ли нам закрыть задачу?"):
            with self.subTest(text=clean):
                self.assertNotIn(S.REVERSE_LABEL, {h["label"] for h in S.scan(clean)["markers"]})

    def test_english_scan(self):
        r = S.scan_en("Great question! It's not just a cache, it's a strategy. Let's dive in. We delve into the tapestry of tests.")
        labels = {h["label"] for h in r["markers"]}
        self.assertTrue({"en: chatbot residue", "en: not X but Y", "en: staged opener"} <= labels)
        self.assertTrue(any(f.startswith("AI words") for f in r["flags"]))
        clean = S.scan_en("The cache keeps responses for ten minutes, so repeat requests skip the database.")
        self.assertEqual((clean["markers"], clean["flags"]), ([], []))

    def test_glyphs_instead_of_words(self):
        r = S.scan("Цена упала: $0,14 → $0,045. Рост ~9% в год. Habr · MIT · 3 звезды.")
        self.assertTrue(any(f.startswith("значки вместо слов") for f in r["flags"]))
        self.assertFalse(any(f.startswith("значки") for f in S.scan("Цена упала с 14 до 4 центов.")["flags"]))

    def test_english_mix_flagged(self):
        r = S.scan(
            "Окно имеет hard cap. Каждый tool call пишет result в историю. Старые results делаем drop, "
            "оставляем summary. Агент сам делает read file и пишет notes, а latency растёт."
        )
        self.assertTrue(any(f.startswith("английские слова") for f in r["flags"]))

    def test_terms_and_library_names_not_counted(self):
        text = (
            "Извлечение (retrieval, RAG, read file) кладёт в окно фрагменты базы. Долю ушедших называют churn, "
            "от английского average revenue per user считают ARPU. Модель Claude пишет код на numpy и pandas, "
            "а сборку ведёт gradle. Команда `git push --force --results` здесь не нужна, ссылку "
            "https://example.com/read/file тоже не считаем."
        )
        self.assertEqual(S.english_mix(S.mask_foreign(text)), [])
        self.assertEqual(S.english_mix("Агент делает read file, потом drop."), ["read file", "drop"])

    def test_english_paragraph_is_not_mix(self):
        abstract = "The article discusses the results of the study and the main issues of the next steps. " * 3
        self.assertFalse(any(f.startswith("английские слова") for f in S.scan("Аннотация.\n\n" + abstract)["flags"]))


def _deck(open_tag, close_tag, n=4):
    return "".join(f"{open_tag}<h2>Выручка выросла на {i}0%</h2><p>Текст слайда {i}.</p>{close_tag}" for i in range(n))


class TestHtmlDeckDetection(unittest.TestCase):
    def test_report_with_sections_is_prose(self):
        self.assertIsNone(S._html_slides(_deck("<section>", "</section>")))
        self.assertIsNone(S._html_slides(_deck('<section class="hero card">', "</section>")))

    def test_slide_class_is_deck(self):
        self.assertEqual(len(S._html_slides(_deck('<div class="slide dark">', "</div>"))), 4)

    def test_slide_prefixed_class_is_not_slide(self):
        self.assertIsNone(S._html_slides(_deck('<div class="slide-title">', "</div>")))

    def test_reveal_js_sections_are_deck(self):
        html = '<div class="reveal"><div class="slides">' + _deck("<section>", "</section>") + "</div></div>"
        self.assertEqual(len(S._html_slides(html)), 4)


class TestCompareUsesSlides(unittest.TestCase):
    def test_compare_passes_slides_for_decks(self):
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as d:
            paths = []
            for name in ("before.html", "after.html"):
                p = os.path.join(d, name)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(_deck('<section class="slide">', "</section>"))
                paths.append(p)
            seen = []
            real = S.scan

            def spy(raw, genre=None, slides=None, foreign=False):
                seen.append(slides)
                return real(raw, genre, slides, foreign)

            argv = ["slop_scan.py", "--compare", *paths]
            with mock.patch.object(S, "scan", spy), mock.patch.object(sys, "argv", argv), mock.patch("sys.stdout"):
                S.main()
        self.assertEqual(len(seen), 2)
        self.assertTrue(all(s is not None and len(s) == 4 for s in seen))


BODY = (
    "С 1 октября зарплаты части бюджетников вырастут в среднем на 4%, и коснётся это не всех. "
    "Повышение получат сотрудники федеральных учреждений, которых не затронули майские указы.\n\n"
    "Военным и силовикам зарплаты проиндексируют в 2022 и 2023 годах, об этом сообщил Минфин.\n\n"
    "До пятницы пришли в бухгалтерию список сотрудников отдела, которым положена индексация."
)


def layout(text, genre=None):
    return [f for f in S.scan(text, genre)["flags"] if f.startswith("вид:")]


class LayoutTests(unittest.TestCase):
    def test_title_and_plain_paragraphs_are_clean(self):
        self.assertEqual(layout("# Индексация зарплат бюджетников с 1 октября\n\n" + BODY), [])
        self.assertEqual(layout("Привет.\n\n" + BODY), [])

    def test_hero_block_under_title(self):
        for sub in ("*Краткая справка для отдела*", "**Дата:** 1 октября 2026", "21 ноября 2026", "Статус: черновик"):
            flags = layout(f"# Индексация зарплат\n\n{sub}\n\n{BODY}")
            self.assertTrue(any("шапка" in f for f in flags), sub)
        note = "Итоги встречи с командой\n\nАня берёт интеграцию с amoCRM. Срок 12 декабря.\n\n" + BODY
        self.assertEqual(layout(note), [])

    def test_boilerplate_sections_and_heading_density(self):
        text = f"# Индексация\n\n## Кратко\n\n{BODY}\n\n## Контекст\n\nМинфин подтвердил сроки.\n\n## Следующие шаги\n\nСобрать список."
        flags = layout(text)
        self.assertTrue(any("шаблонные разделы" in f and "Кратко" in f for f in flags))
        self.assertTrue(any("заголовков 4" in f for f in flags))

    def test_label_lines(self):
        labels = "Срок — две недели.\n\nПервый: прибор учёта в здании. Он покажет, сколько тепла дом получает.\n\n- **Доля рынка:** 0,5%\n"
        self.assertTrue(any("строк-ярлыков «Слово: пояснение» 3" in f for f in layout(BODY + "\n\n" + labels)))
        ordinary = "Shadow DOM – штука уже не новая, её начали использовать производители браузеров ещё несколько лет назад.\n\n" * 3
        self.assertEqual(layout(BODY + "\n\n" + ordinary), [])

    def test_bold_lead_and_bold_count(self):
        items = "\n".join(f"- **Пункт {i}** описывает отдельную часть работы отдела." for i in range(1, 4))
        self.assertTrue(any("жирным началом 3" in f for f in layout(BODY + "\n\n" + items)))
        bold = "Тут **раз**, потом **два**, затем **три** и ещё **четыре** выделения в одном абзаце."
        self.assertTrue(any("жирных выделений 4" in f for f in layout(BODY + "\n\n" + bold)))

    def test_echo_ending_and_opener_about_document(self):
        self.assertTrue(any("концовка-повтор" in f for f in layout(BODY + "\n\nТаким образом, индексация важна для отрасли.")))
        self.assertTrue(any("вступление о самом документе" in f for f in layout("В этом документе мы рассмотрим индексацию зарплат.\n\n" + BODY)))

    def test_reference_doc_with_code_keeps_headings_and_labels(self):
        ref = (
            "# Сканер\n\n## Установка\n\n```bash\npip install x\n```\n\n## Запуск\n\n```bash\nscan file\n```\n\n"
            "## Параметры\n\n- Жанр: глушит маркеры жанра.\n- Язык: выбирает набор правил.\n- Формат: печатает JSON.\n"
        )
        self.assertEqual(layout(ref), [])
        self.assertEqual(layout(ref.replace("```bash", "").replace("```", ""), "tech"), [])
        self.assertTrue(layout(ref.replace("```bash", "").replace("```", "")))

    def test_frontmatter_and_tables_are_not_labels(self):
        text = "---\nname: x\ndescription: y\nlicense: MIT\n---\n\n" + BODY + "\n\n| Срок: | две недели |\n| Доля: | 0,5% |\n| Цена: | 100 |\n"
        self.assertEqual(layout(text), [])

    def test_slides_skip_layout(self):
        self.assertEqual([f for f in S.scan("# Итог\n\n- Срок: неделя", None, [("Итог", ["Срок: неделя"])])["flags"] if f.startswith("вид:")], [])

    def test_report_prints_layout_first(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            S.report(S.scan("# Индексация\n\n**Дата:** 1 октября 2026\n\n" + BODY))
        out = buf.getvalue()
        self.assertIn("ВИДНО ДО ЧТЕНИЯ", out)
        self.assertNotIn("СТРУКТУРА И РИТМ\n  - вид:", out)

    def test_html_markup_reaches_layout(self):
        para = "<p>" + BODY.replace("\n\n", "</p><p>") + "</p>"
        hero = S.scan(S._html_text('<h1>Индексация зарплат</h1><p class="lead">Короткая справка</p><div class="meta"><span class="chip">2026</span></div>' + para))
        self.assertTrue(any("блок под заголовком в разметке: lead, meta, chip" in f for f in hero["flags"]))
        plain = S.scan(S._html_text("<h1>Индексация зарплат бюджетников</h1>" + para))
        self.assertEqual([f for f in plain["flags"] if f.startswith("вид:")], [])
        sections = S.scan(S._html_text("<h2>Кратко</h2>" + para + "<h2>Итог</h2>" + para))
        self.assertTrue(any("шаблонные разделы «Кратко», «Итог»" in f for f in sections["flags"]))
        cards = '<div class="card">Первый блок</div><div class="card">Второй блок</div><div class="tag">метка</div>'
        self.assertTrue(any("карточек и плашек 3" in f for f in S.scan(S._html_text(para + cards))["flags"]))
        # страница-приложение с формой: карточки там часть интерфейса
        app = S.scan(S._html_text(para + cards + '<form><input name="q"></form>'))
        self.assertFalse(any("карточек" in f for f in app["flags"]))

    def test_docx_styles_become_headings(self):
        def p(text, style=None):
            st = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
            return f"<w:p>{st}<w:r><w:t>{text}</w:t></w:r></w:p>"

        text = S._docx_text(p("Отчёт", "Title") + p("Кратко", "Heading1") + p("Пункт списка", "ListParagraph") + p("Обычный абзац."))
        self.assertEqual(text, "# Отчёт\n\n# Кратко\n\n- Пункт списка\n\nОбычный абзац.")


if __name__ == "__main__":
    unittest.main()
