"""Tests hors ligne des règles éditoriales (spec/). Lancer : python -m unittest test_rules -v"""
import json
import unittest

import rules
import specs
from llm_browser import parse_answer

NB = " "


def apply(html, abbrevs=None):
    return rules.apply_all(html, abbrevs)


class SpecsReading(unittest.TestCase):
    def test_pdfs_are_read_and_contain_key_rules(self):
        text = specs.load_specs("spec", {"Guide de rédaction des références bibliographiques.pdf": "Qu'est-ce que Zotero"})
        for needle in ["Titres en H3, sous-titres en H4", "double crochets", "Enable Monarch", "XX<sup>e</sup>",
                       "Ibidem", "SOURCES", "LITTERATURE SECONDAIRE"]:
            self.assertIn(needle, text)
        self.assertNotIn("Qu'est-ce que Zotero", text)
        self.assertNotIn("Revues d’histoire médiévale", text)  # section hors sujet coupée

    def test_missing_marker_fails_loudly(self):
        with self.assertRaises(ValueError):
            specs.load_specs("spec", {"Guide de rédaction des références bibliographiques.pdf": "MARQUEUR INEXISTANT"})


class SourceFootnotes(unittest.TestCase):
    """Cas réel (Logos) : le mode précision de trafilatura perd le texte de la note 1 et numérote mal la note 2."""
    # la note 2 est un <sup>2</sup> « nu » (sans lien), comme dans la vraie page
    PRECISE = ("Texte.[<sup>1</sup>](#easy-footnote-bottom-1-9) Suite.<sup>2</sup>\n\n"
               "1. [*Jesus as Israel*](http://x), the two-volume commentary.")
    RECALL = ("Texte.[<sup>1</sup>](#easy-footnote-bottom-1-9) Suite.<sup>2</sup>\n\n"
              "1. For the “sea”, see Isa 9:1; Luke 21:25.2. For more on this, see [*Jesus as Israel*](http://x), the two-volume commentary.")

    def test_lost_notes_are_recovered_and_numbered(self):
        from extract import _with_footnotes
        out = _with_footnotes(self.PRECISE, self.RECALL)
        self.assertIn("Texte. [NOTE 1] Suite. [NOTE 2]", out)
        self.assertIn("NOTE 1 : For the “sea”, see Isa 9:1; Luke 21:25.", out)
        self.assertIn("NOTE 2 : For more on this, see [*Jesus as Israel*]", out)
        self.assertNotIn("\n1. [*Jesus", out)  # reste mal numéroté retiré
        self.assertEqual(out.count("Jesus as Israel"), 1)

    def test_related_articles_section_removed(self):
        from extract import _RELATED_TAIL
        text = "Corps.\n\n## Related articles\n\n- [A](https://a.org/)\n- [B](https://b.org/)\n"
        self.assertEqual(_RELATED_TAIL.sub("", text).rstrip(), "Corps.")
        keep = "Corps.\n\n## Related ideas\n\nUn vrai paragraphe de texte."
        self.assertEqual(_RELATED_TAIL.sub("", keep), keep)  # pas une simple liste de liens : conservé

    def test_related_section_removed_even_when_a_misnumbered_note_follows(self):
        """Cas réel Logos : la liste « Related articles » précède un reste de note numéroté « 1. »."""
        from extract import _with_footnotes
        precise = ("Texte.<sup>1</sup>\n\n## Related articles\n\n- [A](https://a.org/)\n- [B](https://b.org/)\n\n"
                   "1. [*Livre*](http://x), le commentaire.")
        recall = precise.replace("1. [*Livre*](http://x), le commentaire.", "1. Voir Es 9:1. [*Livre*](http://x), le commentaire.")
        out = _with_footnotes(precise, recall)
        self.assertNotIn("Related articles", out)
        self.assertNotIn("https://a.org/", out)
        self.assertIn("NOTE 1 : Voir Es 9:1.", out)

    def test_notes_as_numbered_headings_are_recognised(self):
        """Cas réel christoverall.com : notes en titres « ###### n. texte » + appels <sup>n</sup> sans lien."""
        from extract import _with_footnotes
        text = ("Premier paragraphe.<sup>1</sup>\n\n###### 1. Label très utilisé.\n\n## Un intertitre\n\n"
                "Second paragraphe.<sup>2</sup> Suite.\n\n###### 2. Autre note.\n\nFin.")
        out = _with_footnotes(text, text)
        self.assertIn("Premier paragraphe. [NOTE 1]", out)
        self.assertIn("Second paragraphe. [NOTE 2] Suite.", out)
        self.assertIn("NOTE 1 : Label très utilisé.", out)
        self.assertIn("NOTE 2 : Autre note.", out)
        self.assertNotIn("######", out)
        self.assertIn("## Un intertitre", out)

    def test_numbered_section_headings_are_not_notes(self):
        from extract import _with_footnotes
        text = "## 1. Introduction\n\nTexte.\n\n## 2. Méthode\n\nSuite."
        self.assertEqual(_with_footnotes(text, text), text)

    def test_bare_sup_is_not_a_note_call_without_notes(self):
        from extract import _with_footnotes
        self.assertEqual(_with_footnotes("Un 10<sup>2</sup> pour cent.", "Un 10<sup>2</sup> pour cent."), "Un 10<sup>2</sup> pour cent.")

    def test_no_notes_only_markers_converted(self):
        from extract import _with_footnotes
        out = _with_footnotes("Un.[<sup>3</sup>](#x) deux.", "Un.[<sup>3</sup>](#x) deux.")
        self.assertEqual(out, "Un. [NOTE 3] deux.")

    def test_numbered_body_list_is_kept(self):
        from extract import _with_footnotes
        both = "Intro.\n\n1. Premier point.\n\n2. Deuxième point."
        self.assertEqual(_with_footnotes(both, both), both)


class Headings(unittest.TestCase):
    def test_h2_h3_become_h3_h4(self):
        out, rep = apply("<h2>Titre</h2><p>a</p><h3>Sous</h3><p>b</p>")
        self.assertIn("<h3>Titre</h3>", out)
        self.assertIn("<h4>Sous</h4>", out)

    def test_single_level_becomes_h3(self):
        out, _ = apply("<h2>A</h2><p>x</p><h2>B</h2>")
        self.assertEqual(out.count("<h3>"), 2)
        self.assertNotIn("<h2", out)


class Ordinals(unittest.TestCase):
    def test_siecles(self):
        out, _ = apply("<p>Au XXème siècle, au XIXe et au XVIIIeme. Le 3ème jour.</p>")
        self.assertIn("XX<sup>e</sup> siècle", out)
        self.assertIn("XIX<sup>e</sup> et", out)
        self.assertIn("XVIII<sup>e</sup>.", out)
        self.assertIn("3<sup>e</sup> jour", out)

    def test_ordinary_words_untouched(self):
        out, _ = apply("<p>De plus, Dieu est Ce que Me Dupont dit. Cie.</p>")
        self.assertNotIn("<sup>", out)

    def test_html_attributes_untouched(self):
        out, _ = apply('<p><a href="https://x.org/XXe/page">lien</a></p>')
        self.assertIn('href="https://x.org/XXe/page"', out)


class Quotes(unittest.TestCase):
    def test_straight_and_curly_become_guillemets_with_nbsp(self):
        out, _ = apply('<p>Il dit "bonjour" et “salut” à tous.</p>')
        self.assertIn(f"«{NB}bonjour{NB}»", out)
        self.assertIn(f"«{NB}salut{NB}»", out)
        self.assertNotIn('"', out)

    def test_nested_quotes_use_english_inside(self):
        out, _ = apply("<p>Il dit “elle a dit “non” hier” sans doute.</p>")
        self.assertIn(f"«{NB}elle a dit “non” hier{NB}»", out)

    def test_entities_and_spaces_normalized(self):
        out, _ = apply("<p>&laquo; texte &raquo; et «autre»</p>")
        self.assertIn(f"«{NB}texte{NB}»", out)
        self.assertIn(f"«{NB}autre{NB}»", out)
        self.assertNotIn(NB * 2, out)

    def test_odd_straight_quote_is_left_and_warned(self):
        out, rep = apply('<p>Il a dit " seulement.</p>')
        self.assertIn('"', out)
        self.assertTrue(any("impair" in w for w in rep.warnings))

    def test_attributes_not_touched(self):
        out, _ = apply('<p><a href="https://x.org">lien</a> "mot"</p>')
        self.assertIn('href="https://x.org"', out)


class Notes(unittest.TestCase):
    def test_spec_example_unchanged(self):
        """Forme de l'exemple de la spec, avec une citation traduite entre « » (cas où la balise est justifiée)."""
        html = "<p>Texte texte texte[[[Traduction libre] « note note » note note (NDT.).]].</p>"
        out, rep = apply(html)
        self.assertIn(f"texte[[[Traduction libre] «{NB}note note{NB}» note note (NDT.).]].", out)
        # seul avertissement attendu : toute note (NDT.) est signalée pour relecture
        self.assertEqual(len(rep.warnings), 1)
        self.assertIn("NDT", rep.warnings[0])

    def test_ndt_note_is_flagged_for_review(self):
        _, rep = apply("<p>Texte[[Explication (NDT.).]].</p>")
        self.assertTrue(any("NDT" in w for w in rep.warnings))

    def test_traduction_libre_removed_when_no_quotation(self):
        out, rep = apply("<p>Texte[[[Traduction libre] Voir Dupont, Livre, 2000.]].</p>")
        self.assertIn("Texte[[Voir Dupont, Livre, 2000.]].", out)
        self.assertTrue(any("Traduction libre" in f for f in rep.fixes))

    def test_four_brackets_normalised(self):
        out, _ = apply("<p>Texte[[[[Traduction libre] « citation » suite.]].</p>")
        self.assertIn("[[[Traduction libre]", out)
        self.assertNotIn("[[[[", out)

    def test_note_moved_before_punctuation(self):
        out, _ = apply("<p>Une phrase.[[Note.]]</p>")
        self.assertIn("phrase[[Note.]].", out)

    def test_note_without_final_punctuation_gets_one(self):
        out, _ = apply("<p>Texte[[une note sans point]] suite.</p>")
        self.assertIn("[[une note sans point.]]", out)

    def test_separator_added_at_the_very_end_when_notes(self):
        out, _ = apply("<p>Texte[[Note.]].</p>")
        self.assertTrue(out.rstrip().endswith("<hr>"))

    def test_no_separator_without_notes(self):
        out, _ = apply("<p>Texte.</p>")
        self.assertNotIn("<hr", out)

    def test_empty_invented_note_is_removed(self):
        out, rep = apply("<p>Un mot[[Traduction libre.]] puis[[Vraie note.]] fin.</p>")
        self.assertNotIn("Traduction libre.]]", out)
        self.assertIn("puis[[Vraie note.]]", out)
        self.assertTrue(any("Note vide" in f for f in rep.fixes))

    def test_unbalanced_brackets_warned(self):
        _, rep = apply("<p>Texte[[Note sans fin.</p>")
        self.assertTrue(any("non appariés" in w for w in rep.warnings))

    def test_quote_in_note_without_traduction_libre_warned(self):
        _, rep = apply("<p>Texte[[Il écrit « bonjour ».]].</p>")
        self.assertTrue(any("Traduction libre" in w for w in rep.warnings))


class BibleRefs(unittest.TestCase):
    def test_comma_format_and_full_name_when_isolated(self):
        out, _ = apply("<p>Voir Jérémie 29:11 et Jean 3.16, ainsi que 1 Corinthiens 13:4.</p>")
        self.assertIn("Jérémie 29,11", out)
        self.assertIn("Jean 3,16", out)
        self.assertIn("1 Corinthiens 13,4", out)

    def test_spelling_follows_segond21_list(self):
        out, _ = apply("<p>Ésaïe 53:5 et Éphésiens 2:8.</p>")
        self.assertIn("Esaïe 53,5", out)
        self.assertIn("Ephésiens 2,8", out)

    def test_abbreviation_in_note_and_list_when_provided(self):
        ab = {"Jean": "Jn"}
        out, _ = apply("<p>Texte Jean 3:16[[Voir Jean 3:16.]]</p><ul><li>Jean 3:16</li></ul>", ab)
        self.assertIn("Texte Jean 3,16", out)  # référence isolée : nom entier
        self.assertIn("[[Voir Jn 3,16.]]", out)  # en note : abrégé
        self.assertIn("<li>Jn 3,16</li>", out)  # en liste : abrégé

    def test_abbreviation_file_covers_all_66_books_uniquely(self):
        import bible
        ab = bible.load_abbreviations()
        self.assertEqual(set(ab), set(bible.BOOKS))
        self.assertEqual(len(bible.BOOKS), 66)
        self.assertEqual(len(set(ab.values())), 66)  # aucune abréviation en double
        # colonne « Jérus. » du tableau de Lacroux (Orthotypographie)
        self.assertEqual((ab["Genèse"], ab["Romains"], ab["Jean"], ab["1 Corinthiens"]), ("Gn", "Rm", "Jn", "1 Co"))
        self.assertEqual((ab["Ecclésiaste"], ab["Cantique des Cantiques"], ab["Esaïe"], ab["Malachie"], ab["Jacques"]),
                         ("Qo", "Ct", "Is", "Ml", "Jc"))

    def test_real_abbreviations_applied_in_notes_and_lists_only(self):
        import bible
        ab = bible.load_abbreviations()
        out, rep = apply("<p>Voir Romains 8:28[[Cf. Romains 8:28 ; Genèse 1:1.]]</p><ul><li>1 Corinthiens 13:4</li></ul>", ab)
        self.assertIn("Voir Romains 8,28", out)  # isolée : en toutes lettres
        self.assertIn("[[Cf. Rm 8,28 ; Gn 1,1.]]", out)  # note : abrégé
        self.assertIn("<li>1 Co 13,4</li>", out)  # liste : abrégé
        self.assertFalse(any("abréviations non fournies" in w for w in rep.warnings))

    def test_missing_abbreviations_warn_instead_of_inventing(self):
        out, rep = apply("<p>Texte[[Voir Jean 3:16.]]</p>")
        self.assertIn("Voir Jean 3,16.", out)
        self.assertTrue(any("abréviations non fournies" in w for w in rep.warnings))

    def test_time_is_not_a_reference(self):
        out, _ = apply("<p>Rendez-vous à 10:30.</p>")
        self.assertIn("10:30", out)


class Slug(unittest.TestCase):
    TITLE = "Quels sont les « projets » de Dieu pour vous ? Ce que signifie vraiment Jérémie 29,11"

    def test_example_of_the_editor(self):
        self.assertEqual(rules.make_slug("projets-dieu-jeremie-2911", self.TITLE), ("projets-dieu-jeremie-2911", False))

    def test_determiners_and_function_words_are_removed_from_llm_slug(self):
        self.assertEqual(rules.clean_slug("les-projets-de-dieu-pour-vous-jeremie-29-11"), "projets-dieu-jeremie-29-11")
        self.assertEqual(rules.clean_slug("Quels sont les projets de Dieu"), "projets-dieu")

    def test_verse_numbers_are_glued(self):
        self.assertEqual(rules.clean_slug("Jérémie 29,11"), "jeremie-2911")
        self.assertEqual(rules.clean_slug("Romains 8:28"), "romains-828")

    def test_accents_case_and_ligatures(self):
        self.assertEqual(rules.clean_slug("Ésaïe 53,5 : le Serviteur ; cœur"), "esaie-535-serviteur-coeur")

    def test_length_limits(self):
        s = rules.clean_slug("alpha bravo charlie delta echo foxtrot golf hotel")
        self.assertEqual(s, "alpha-bravo-charlie-delta-echo-foxtrot")  # 6 mots maximum
        long = rules.clean_slug(" ".join(["abcdefghij"] * 6))
        self.assertLessEqual(len(long), 60)

    def test_slug_is_url_safe(self):
        s = rules.clean_slug("Noël ? « Fête » & <b>joie</b> !")
        self.assertRegex(s, r"^[a-z0-9]+(-[a-z0-9]+)*$")

    def test_fallback_to_title_when_llm_gives_nothing_usable(self):
        title = "Les chapitres de la maternité : comment la lecture façonne un enfant"
        self.assertEqual(rules.make_slug(None, title), (rules.clean_slug(title), True))
        self.assertEqual(rules.make_slug("les de la", title)[1], True)  # que des mots vides -> repli sur le titre
        self.assertTrue(rules.make_slug(None, title)[0].startswith("chapitres-maternite"))

    def test_parse_answer_reads_slug_in_any_order(self):
        a = parse_answer("TITRE: T\nTAGS: a\nSLUG: projets-dieu\nCATEGORIE: Théologie\n---\n<p>Le texte est la et des.</p>\n<!--FIN-->")
        self.assertEqual((a.slug, a.category), ("projets-dieu", "Théologie"))
        b = parse_answer("TITRE: T\nTAGS: a\nCATEGORIE: aucune\nSLUG: x-y\n---\n<p>Le texte est la et des.</p>\n<!--FIN-->")
        self.assertEqual((b.slug, b.category), ("x-y", None))
        c = parse_answer("TITRE: T\nTAGS: a\n---\n<p>Le texte est la et des.</p>\n<!--FIN-->")
        self.assertIsNone(c.slug)

    def test_pipeline_returns_clean_slug(self):
        from extract import Article
        from pipeline import translate_article
        import tomllib
        from pathlib import Path
        cfg = tomllib.loads(Path("config.toml").read_text(encoding="utf-8"))
        cfg["llm"]["engines"] = ["gemini"]
        text = "Some text without footnotes at all. " * 10
        answer = ("TITRE: Quels sont les « projets » de Dieu\nTAGS: a\nCATEGORIE: aucune\n"
                  "SLUG: Les-Projets-de-Dieu-Jérémie-29,11\n---\n<p>Le texte est la et des.</p>\n<!--FIN-->")
        res = translate_article(Article("https://example.com/a", "Original", text), cfg, FakeBrowser([answer]))
        self.assertEqual(res.slug, "projets-dieu-jeremie-2911")
        self.assertTrue(any("nettoyé" in f for f in res.fixes))

    def test_pipeline_falls_back_to_title(self):
        from extract import Article
        from pipeline import translate_article
        import tomllib
        from pathlib import Path
        cfg = tomllib.loads(Path("config.toml").read_text(encoding="utf-8"))
        cfg["llm"]["engines"] = ["gemini"]
        res = translate_article(Article("https://example.com/a", "Original", "Texte source sans note. " * 10), cfg,
                                FakeBrowser([raw(GOOD)]))  # réponse sans ligne SLUG
        self.assertEqual(res.slug, "titre")  # titre « Un titre » -> « titre » (« un » retiré)
        self.assertTrue(any("construit à partir du titre" in f for f in res.fixes))


class OAuthScope(unittest.TestCase):
    def test_least_privilege_url(self):
        from urllib.parse import parse_qs, urlparse
        import wp
        q = parse_qs(urlparse(wp.authorize_url("123", "posts taxonomy", "monsite.wordpress.com")).query)
        self.assertEqual(q["scope"], ["posts taxonomy"])
        self.assertEqual(q["blog"], ["monsite.wordpress.com"])
        self.assertEqual(q["client_id"], ["123"])

    def test_default_url_has_no_scope(self):
        from urllib.parse import parse_qs, urlparse
        import wp
        q = parse_qs(urlparse(wp.authorize_url("123")).query)
        self.assertNotIn("scope", q)
        self.assertNotIn("blog", q)

    def test_config_asks_for_posts_and_taxonomy_only(self):
        import tomllib
        from pathlib import Path
        cfg = tomllib.loads(Path("config.toml").read_text(encoding="utf-8"))
        self.assertEqual(set(cfg["wordpress"]["scope"].split()), {"posts", "taxonomy"})

    def test_only_write_call_creates_a_draft(self):
        """Garde-fou de code : le seul envoi de contenu à WordPress force status=draft."""
        import inspect
        import wp
        src = inspect.getsource(wp.create_draft)
        self.assertIn('"status": "draft"', src)
        self.assertEqual(inspect.getsource(wp).count("requests.post("), 2)  # jeton OAuth + création du brouillon
        self.assertNotIn("requests.delete", inspect.getsource(wp))
        self.assertNotIn("requests.put", inspect.getsource(wp))


class SelfHosted(unittest.TestCase):
    """wp_selfhosted : brouillon via /wp-json/wp/v2 avec mot de passe d'application (réseau simulé)."""

    @staticmethod
    def resp(status=200, data=None):
        from unittest.mock import MagicMock
        r = MagicMock()
        r.status_code = status
        r.json.return_value = data
        r.text = json.dumps(data) if data is not None else ""
        r.raise_for_status.side_effect = None if status < 400 else RuntimeError(f"HTTP {status}")
        return r

    def run_create(self, get_map, post_map, tags=("Foi", "Nouveau"), cats=("Théologie",), slug="projets-dieu"):
        from unittest.mock import patch
        import wp_selfhosted as ws
        posted = []

        def fake_get(url, params=None, **kw):
            return get_map(url, params)

        def fake_post(url, json=None, **kw):
            posted.append((url, json))
            return post_map(url, json)

        with patch.object(ws.requests, "get", fake_get), patch.object(ws.requests, "post", fake_post), \
                patch.object(ws, "_auth", return_value=("agent", "xxxx")):
            url = ws.create_draft("parlafoi.fr", "Titre", "<p>x</p>", list(tags), list(cats), slug)
        return url, posted

    def test_draft_payload_and_edit_url(self):
        def get_map(url, params):
            if url.endswith("/tags"):
                return self.resp(data=[{"id": 7, "name": "Foi"}] if params["search"] == "Foi" else [])
            return self.resp(data=[{"id": 3, "name": "Théologie"}])

        def post_map(url, payload):
            if url.endswith("/tags"):
                return self.resp(201, {"id": 8})
            return self.resp(201, {"id": 42})

        url, posted = self.run_create(get_map, post_map)
        self.assertEqual(url, "https://parlafoi.fr/wp-admin/post.php?post=42&action=edit")
        post_payload = [p for u, p in posted if u.endswith("/posts")][0]
        self.assertEqual(post_payload["status"], "draft")
        self.assertEqual(post_payload["slug"], "projets-dieu")
        self.assertEqual(post_payload["tags"], [7, 8])  # « Foi » existait, « Nouveau » a été créée
        self.assertEqual(post_payload["categories"], [3])

    def test_tag_not_creatable_by_contributor_is_skipped_not_fatal(self):
        def get_map(url, params):
            return self.resp(data=[])

        def post_map(url, payload):
            if url.endswith("/tags"):
                return self.resp(403, {"code": "rest_cannot_create"})
            return self.resp(201, {"id": 5})

        _, posted = self.run_create(get_map, post_map, cats=())
        post_payload = [p for u, p in posted if u.endswith("/posts")][0]
        self.assertNotIn("tags", post_payload)
        self.assertEqual(post_payload["status"], "draft")

    def test_categories_are_never_created(self):
        def get_map(url, params):
            return self.resp(data=[])

        def post_map(url, payload):
            return self.resp(201, {"id": 5})

        _, posted = self.run_create(get_map, post_map, tags=(), cats=("Inconnue",))
        self.assertFalse(any(u.endswith("/categories") for u, _ in posted))

    def test_code_never_publishes_updates_or_deletes(self):
        import inspect
        import wp_selfhosted
        src = inspect.getsource(wp_selfhosted)
        self.assertIn('"status": "draft"', src)
        self.assertNotIn("requests.delete", src)
        self.assertNotIn("requests.put", src)
        self.assertNotIn("requests.patch", src)
        self.assertNotRegex(src, r"""status["']\s*:\s*["'](publish|future|private|pending)["']""")

    def test_backend_selection(self):
        import agent
        import wp
        import wp_selfhosted
        self.assertIs(agent.backend({"wordpress": {"mode": "selfhosted"}}), wp_selfhosted)
        self.assertIs(agent.backend({"wordpress": {"mode": "wpcom"}}), wp)
        self.assertIs(agent.backend({"wordpress": {}}), wp)  # défaut : ancien comportement
        with self.assertRaises(ValueError):
            agent.backend({"wordpress": {"mode": "autre"}})

    def test_state_database_is_per_site(self):
        import os
        import agent
        for site, expected in [("parlafoi.fr", "state-parlafoi-fr.db"),
                               ("https://parlafoi.fr", "state-parlafoi-fr.db"),
                               ("gilbertgertrudetest.wordpress.com", "state-gilbertgertrudetest-wordpress-com.db")]:
            existed = os.path.exists(expected)
            db = agent.open_db(site)
            db.close()
            self.assertTrue(os.path.exists(expected))
            if not existed:
                os.remove(expected)


class Urls(unittest.TestCase):
    def test_bare_url_in_note_keeps_closing_brackets_outside_the_link(self):
        """Cas réel (brouillon 99) : WordPress avalait « .]] » dans l'URL nue."""
        out, _ = apply("<p>Texte[[Voir https://finance.yahoo.com/news/x-081108380.html.]] suite.</p>")
        self.assertIn('<a href="https://finance.yahoo.com/news/x-081108380.html">https://finance.yahoo.com/news/x-081108380.html</a>.]]', out)

    def test_existing_links_untouched(self):
        html = '<p><a href="https://x.org/a">https://x.org/a</a> et <a href="https://y.org">y</a></p>'
        out, _ = apply(html)
        self.assertEqual(out, html)

    def test_url_followed_by_comma_or_parenthesis(self):
        out, _ = apply("<p>Voir (https://x.org/p), puis https://y.org/q, enfin.</p>")
        self.assertIn('(<a href="https://x.org/p">https://x.org/p</a>),', out)
        self.assertIn('<a href="https://y.org/q">https://y.org/q</a>, enfin', out)


class Tags(unittest.TestCase):
    def test_unexpected_tags_removed_text_kept(self):
        out, rep = apply("<p>Fin<mark>.</mark> <span class='x'>Texte</span> <i>it</i> <b>gras</b> <a href=\"https://x.org\">l</a></p>")
        self.assertNotIn("<mark", out)
        self.assertNotIn("<span", out)
        self.assertIn("Fin. Texte", out)
        self.assertIn("<em>it</em>", out)
        self.assertIn("<strong>gras</strong>", out)
        self.assertIn('<a href="https://x.org">l</a>', out)
        self.assertTrue(any("mark" in f for f in rep.fixes))

    def test_allowed_tags_untouched(self):
        html = "<h3>T</h3><p>a<sup>e</sup><em>b</em></p><ul><li>c</li></ul><blockquote><p>d</p></blockquote>"
        out, _ = apply(html)
        self.assertEqual(out, html)


class LongQuoteWarning(unittest.TestCase):
    def test_single_long_quote_paragraph_warns(self):
        _, rep = apply("<p>« Première phrase. Seconde phrase. »</p>")
        self.assertTrue(any("blockquote" in w for w in rep.warnings))

    def test_dialogue_with_several_short_quotes_does_not_warn(self):
        _, rep = apply("<p>« Pas si vite ! » dit-il. Plus loin. « Vous ? » demande-t-elle. « Non. »</p>")
        self.assertFalse(any("blockquote" in w for w in rep.warnings))


class Separators(unittest.TestCase):
    def test_llm_separators_removed(self):
        out, rep = apply("<p>a</p><hr><p>b</p><hr/><p>c</p>")
        self.assertNotIn("<hr", out)
        self.assertTrue(any("séparateur" in f for f in rep.fixes))

    def test_invented_cover_caption_removed(self):
        out, rep = apply('<p>Texte.</p>\n<p class="petite">Illustration de couverture : <em>Titre</em>, Auteur.</p>')
        self.assertNotIn("Illustration de couverture", out)
        self.assertIn("Texte.", out)
        self.assertTrue(any("Légende" in f for f in rep.fixes))

    def test_markdown_dashes_removed(self):
        out, _ = apply("<p>a</p>\n\n---\n<p>b</p>\n---")
        self.assertNotIn("---", out)

    def test_only_final_separator_with_notes(self):
        out, _ = apply("<p>Texte[[Note.]].</p><hr><p>Suite.</p>")
        self.assertEqual(out.count("<hr>"), 1)
        self.assertTrue(out.rstrip().endswith("<hr>"))


class Intro(unittest.TestCase):
    def test_intro_is_italic_and_followed_by_separator(self):
        intro = rules.build_intro("https://x.org/a?b=1&c=2", "Original <Title>")
        self.assertTrue(intro.startswith("<p><em>Cet article est la traduction de <a href="))
        self.assertIn("&amp;c=2", intro)
        self.assertIn("&lt;Title&gt;", intro)
        self.assertTrue(intro.rstrip().endswith("<hr>"))


class ParseAnswer(unittest.TestCase):
    RAW = ("TITRE: Un titre\nTAGS: a, b\nCATEGORIE: Théologie\n---\n<h3>X</h3><p>Le texte est la.</p>\n"
           "<!--A_VERIFIER: Livre 1 ;; Livre 2-->\n<!--FIN-->")

    def test_full_answer(self):
        a = parse_answer(self.RAW)
        self.assertEqual((a.title, a.tags, a.category), ("Un titre", ["a", "b"], "Théologie"))
        self.assertEqual(a.to_check, ["Livre 1", "Livre 2"])
        self.assertNotIn("A_VERIFIER", a.html)

    def test_a_verifier_rien_is_dropped(self):
        a = parse_answer("TITRE: T\nTAGS: a\n---\n<p>Le texte est la et des.</p>\n<!--A_VERIFIER: rien-->\n<!--FIN-->")
        self.assertEqual(a.to_check, [])
        b = parse_answer("TITRE: T\nTAGS: a\n---\n<p>Le texte est la et des.</p>\n<!--A_VERIFIER: Livre X ; rien-->\n<!--FIN-->")
        self.assertEqual(b.to_check, ["Livre X"])

    def test_category_optional(self):
        a = parse_answer("TITRE: T\nTAGS: a\n---\n<p>Le texte est la et des.</p>\n<!--FIN-->")
        self.assertIsNone(a.category)

    def test_category_aucune(self):
        a = parse_answer("TITRE: T\nTAGS: a\nCATEGORIE: aucune\n---\n<p>Le texte est la et des.</p>\n<!--FIN-->")
        self.assertIsNone(a.category)

    def test_untranslated_answer_rejected(self):
        with self.assertRaises(ValueError):
            parse_answer("TITRE: T\nTAGS: a\n---\n<p>The text is the one of the and that.</p>\n<!--FIN-->")


class FakeBrowser:
    """Rejoue des réponses de LLM préparées ; lève LLMUnavailable pour un élément None."""
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def translate(self, engine, prompt, timeout_s=600):
        from llm_browser import LLMUnavailable
        self.calls.append(engine)
        a = self.answers.pop(0)
        if a is None:
            raise LLMUnavailable("hors service")
        return a


def raw(body, check="rien"):
    return f"TITRE: Un titre\nTAGS: a, b\nCATEGORIE: aucune\n---\n{body}\n<!--A_VERIFIER: {check}-->\n<!--FIN-->"


GOOD = "<p>Le texte est la et des choses.</p>"
INVENTED = "<p>Le texte[[Une note inventée.]] est la et des choses.</p>"


class PipelineGate(unittest.TestCase):
    CFG = None

    @classmethod
    def setUpClass(cls):
        import tomllib
        from pathlib import Path
        cls.CFG = tomllib.loads(Path("config.toml").read_text(encoding="utf-8"))
        cls.CFG["llm"]["engines"] = ["gemini", "gpt"]

    def art(self, text="Some text without footnotes at all, about Tolkien letters. " * 5):
        from extract import Article
        return Article("https://example.com/a", "Original", text)

    def test_invented_notes_are_never_accepted(self):
        from pipeline import translate_article
        b = FakeBrowser([raw(INVENTED)] * 4)  # 2 moteurs x 2 essais
        with self.assertRaises(RuntimeError) as cm:
            translate_article(self.art(), self.CFG, b)
        self.assertIn("rien n'est publié", str(cm.exception))
        self.assertEqual(b.calls, ["gemini", "gemini", "gpt", "gpt"])

    def test_second_attempt_can_succeed(self):
        from pipeline import translate_article
        b = FakeBrowser([raw(INVENTED), raw(GOOD)])
        res = translate_article(self.art(), self.CFG, b)
        self.assertEqual(b.calls, ["gemini", "gemini"])
        self.assertNotIn("[[", res.html)
        self.assertEqual(res.engine, "gemini")

    def test_fallback_to_second_engine_when_first_unavailable(self):
        from pipeline import translate_article
        b = FakeBrowser([None, raw(GOOD)])
        res = translate_article(self.art(), self.CFG, b)
        self.assertEqual((b.calls, res.engine), (["gemini", "gpt"], "gpt"))

    def test_missing_note_is_rejected_too(self):
        from pipeline import translate_article
        art = self.art("Texte. [NOTE 1] Suite du texte source.\n\n--- NOTES DE BAS DE PAGE DE LA SOURCE ---\n\nNOTE 1 : Voir ceci. " * 3)
        b = FakeBrowser([raw(GOOD)] * 4)
        with self.assertRaises(RuntimeError):
            translate_article(art, self.CFG, b)

    def test_unclosed_note_swallowing_the_next_is_rejected(self):
        """Cas réel (brouillon 94) : la note 1 n'est jamais refermée et absorbe la note 2."""
        from pipeline import translate_article
        art = self.art("A. [NOTE 1] B. [NOTE 2] C.\n\n--- NOTES DE BAS DE PAGE DE LA SOURCE ---\n\nNOTE 1 : Un.\n\nNOTE 2 : Deux.")
        bad = "<p>A[[Un. B[[Deux.]] C.</p>"
        b = FakeBrowser([raw(bad)] * 4)
        with self.assertRaises(RuntimeError):
            translate_article(art, self.CFG, b)

    def test_matching_notes_accepted(self):
        from pipeline import translate_article
        art = self.art("Texte. [NOTE 1] Suite du texte source.\n\n--- NOTES DE BAS DE PAGE DE LA SOURCE ---\n\nNOTE 1 : Voir ceci.")
        res = translate_article(art, self.CFG, FakeBrowser([raw("<p>Le texte[[Voir ceci.]] est la et des.</p>")]))
        self.assertIn("[[Voir ceci.]]", res.html)
        self.assertTrue(res.html.rstrip().endswith("<hr>"))

    def test_to_check_items_not_in_source_are_dropped(self):
        from pipeline import translate_article
        res = translate_article(self.art(), self.CFG,
                                FakeBrowser([raw(GOOD, "BRAUDEL, Fernand, La Méditerranée ;; The Letters of Tolkien")]))
        self.assertEqual(res.to_check, ["The Letters of Tolkien"])
        self.assertTrue(any("écarté" in f for f in res.fixes))


if __name__ == "__main__":
    unittest.main()
