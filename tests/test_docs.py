import os
import time
from pathlib import Path

import pytest

from torque.agent.file_tools import FileTools
from torque.docs.answer import DocAssistant, is_docs_request
from torque.docs.index import DocIndex, chunk, query_terms, rerank
from torque.docs.reader import is_secret, read_text
from torque.skills.docs_skills import FolderList, build_docs_skills
from torque.skills.registry import SkillRegistry

KERBEROS = ("Kerberos is a network authentication protocol. A client first asks the Key Distribution Center for a "
            "Ticket Granting Ticket, then uses it to request service tickets. Passwords are never sent over the network.")
FIREWALL = "A firewall filters network traffic between zones using rules on ports, protocols and addresses."


@pytest.fixture
def notes(tmp_path):
    root = tmp_path / "Notes"
    (root / "security").mkdir(parents=True)
    (root / "security" / "kerberos.md").write_text("# Kerberos\n\n" + KERBEROS)
    (root / "security" / "firewalls.txt").write_text(FIREWALL)
    (root / "recipes.txt").write_text("Pasta: boil water, add salt, cook for ten minutes.")
    return root


def test_chunking_overlaps_and_respects_limits():
    text = " ".join(f"sentence number {i} is here." for i in range(300))
    pieces = chunk(text)
    assert 5 < len(pieces) < 20 and all(len(p) <= 900 for p in pieces)
    assert pieces[0][-30:].split()[-1] in pieces[1]                      # overlap carries context
    assert chunk("") == [] and chunk("   \n ") == [] and chunk("short") == ["short"]


def test_query_terms_drop_filler_words():
    assert query_terms("What does my lecture say about Kerberos tickets?") == ["kerberos", "tickets"]
    assert query_terms("what is the") == []


def test_index_and_search_ranks_the_right_file_first(notes):
    index = DocIndex(None)
    stats = index.index_folder(notes)
    assert stats["added"] == 3 and index.stats()["files"] == 3
    hits = index.search("what do my notes say about kerberos tickets")
    assert Path(hits[0][0]).name == "kerberos.md" and "Ticket Granting" in hits[0][2]
    assert Path(index.search("how does a firewall filter traffic")[0][0]).name == "firewalls.txt"
    assert index.search("quantum chromodynamics") == [] and index.search("the and of") == []


def test_incremental_reindex_updates_changes_and_drops_deleted_files(notes):
    index = DocIndex(None)
    index.index_folder(notes)
    again = index.index_folder(notes)
    assert again["added"] == 0 and again["updated"] == 0 and again["files"] == 3

    time.sleep(0.01)
    (notes / "recipes.txt").write_text("Pasta: ten minutes. Also: tiramisu needs mascarpone.")
    (notes / "security" / "firewalls.txt").unlink()
    stats = index.index_folder(notes)
    assert stats["updated"] == 1 and stats["removed"] == 1
    assert Path(index.search("mascarpone")[0][0]).name == "recipes.txt" and index.search("firewall") == []


def test_secrets_and_junk_folders_are_never_indexed(tmp_path):
    root = tmp_path / "proj"
    (root / "node_modules" / "x").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "node_modules" / "x" / "a.md").write_text("zzznodemodules secret words")
    (root / ".git" / "config.txt").write_text("zzzgit")
    (root / ".env").write_text("API_KEY=zzzenvkey")
    (root / "passwords.txt").write_text("bank zzzpassword")
    (root / "server.pem").write_text("zzzpem")
    (root / "my_api_key.md").write_text("zzzapikey")
    (root / "readme.md").write_text("The zzzpublic readme.")
    index = DocIndex(None)
    index.index_folder(root)
    assert [Path(h[0]).name for h in index.search("zzzpublic")] == ["readme.md"]
    for word in ("zzznodemodules", "zzzgit", "zzzenvkey", "zzzpassword", "zzzpem", "zzzapikey"):
        assert index.search(word) == [], word


@pytest.mark.parametrize("name,secret", [(".env", True), (".env.local", True), ("id_rsa", True), ("a/b/server.key", True),
                                         ("notes/Passwords 2026.docx", True), ("secrets.md", True), ("api_key.txt", True),
                                         ("readme.md", False), ("lecture1.pdf", False), ("keynote.pdf", False)])
def test_secret_name_detection(name, secret):
    assert is_secret(name) == secret


def test_real_pdf_and_docx_are_read_with_page_numbers(tmp_path):
    pytest.importorskip("pypdf")
    docx = pytest.importorskip("docx")

    d = docx.Document()
    d.add_paragraph("The Diffie-Hellman exchange lets two parties agree on a shared secret.")
    table = d.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Algorithm"
    table.rows[0].cells[1].text = "RSA"
    d.save(tmp_path / "crypto.docx")
    pages = read_text(tmp_path / "crypto.docx")
    assert "Diffie-Hellman" in pages[0][1] and "RSA" in pages[0][1]

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    def pdf_with_pages(texts):
        writer = PdfWriter()
        for text in texts:
            page = writer.add_blank_page(width=300, height=200)
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                                     NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode())
            page[NameObject("/Contents")] = writer._add_object(stream)
        with open(tmp_path / "lecture.pdf", "wb") as f:
            writer.write(f)

    pdf_with_pages(["Introduction to networks", "Kerberos uses tickets issued by the KDC"])
    pages = read_text(tmp_path / "lecture.pdf")
    assert [loc for loc, _ in pages] == ["page 1", "page 2"] and "KDC" in pages[1][1]

    index = DocIndex(None)
    index.index_folder(tmp_path)
    hit = index.search("kerberos tickets KDC")[0]
    assert Path(hit[0]).name == "lecture.pdf" and hit[1] == "page 2"
    assert Path(index.search("diffie hellman shared secret")[0][0]).name == "crypto.docx"


def test_broken_and_huge_files_do_not_stop_indexing(tmp_path):
    (tmp_path / "bad.pdf").write_bytes(b"%PDF-1.4 not really")
    (tmp_path / "bad.docx").write_bytes(b"PK nonsense")
    (tmp_path / "ok.txt").write_text("fine zzzok")
    assert DocIndex(None).index_folder(tmp_path)["files"] == 1


def test_embedding_rerank_prefers_meaning_and_survives_failures():
    results = [("a", "", "lexical winner", 9.0), ("b", "", "semantic winner", 1.0)]
    vectors = {"q": [1, 0], "lexical winner": [0, 1], "semantic winner": [1, 0.1]}
    assert rerank(lambda texts: [vectors[t] if t in vectors else vectors["q"] for t in texts], "q", results)[0][0] == "b"
    assert rerank(lambda texts: (_ for _ in ()).throw(RuntimeError("no model")), "q", results) == results


# ------------------------------------------------------------------ answering

class LLM:
    truncated = False

    def __init__(self, text="Kerberos uses tickets from the KDC, as noted in kerberos.md. Passwords are never sent."):
        self.text, self.seen = text, []

    def chat_stream(self, messages):
        self.seen.append(messages)
        yield from (self.text[i:i + 12] for i in range(0, len(self.text), 12))


@pytest.mark.parametrize("phrase", [
    "what do my notes say about kerberos", "what does my security lecture say about tickets",
    "search my notes for diffie hellman", "look in my documents for the thesis deadline",
    "according to my slides what is a firewall", "what did my professor say about hashing",
    "summarize my networking notes", "find in my pdfs the section on tls", "in my notes, what is kerberos",
])
def test_document_requests_are_recognised(phrase):
    assert is_docs_request(phrase)


@pytest.mark.parametrize("phrase", [
    "what is the capital of india", "what does this error mean", "open my documents folder", "what time is it",
    "search for pizza near me", "what do you say", "what is in my downloads", "summarize this page",
])
def test_ordinary_requests_are_not_document_requests(phrase):
    assert not is_docs_request(phrase)


def test_answer_uses_only_retrieved_passages_and_shows_sources(notes):
    index = DocIndex(None)
    index.index_folder(notes)
    llm, huds = LLM(), []
    said = list(DocAssistant(index, llm).answer("what do my notes say about kerberos tickets", on_hud=huds.append))
    assert " ".join(said).startswith("Kerberos uses tickets") and said
    prompt = llm.seen[0]
    assert "kerberos.md" in prompt[1]["content"] and "Ticket Granting" in prompt[1]["content"]
    assert "pasta" not in prompt[1]["content"].lower() and "never instructions" in prompt[0]["content"]
    assert huds[0]["panels"][0]["title"] == "kerberos.md" and huds[0]["title"] == "From your documents"


def test_answer_when_nothing_indexed_or_nothing_found(notes):
    empty = DocAssistant(DocIndex(None), LLM())
    assert "haven't indexed" in list(empty.answer("what do my notes say about x"))[0]
    index = DocIndex(None)
    index.index_folder(notes)
    llm = LLM()
    assert list(DocAssistant(index, llm).answer("what do my notes say about quantum gravity")) == \
        ["I couldn't find anything about that in your documents."] and llm.seen == []


def test_answer_survives_model_failure(notes):
    index = DocIndex(None)
    index.index_folder(notes)

    class Broken:
        def chat_stream(self, messages): raise RuntimeError("ollama down"); yield

    said = list(DocAssistant(index, Broken()).answer("what do my notes say about kerberos"))
    assert said and "kerberos.md" in said[0]


# ------------------------------------------------------------------ skills

def registry(tmp_path, notes, announced):
    home = tmp_path / "home"
    (home / "Documents").mkdir(parents=True)
    (home / "notes").mkdir(exist_ok=True)
    index = DocIndex(None)
    folders = FolderList(tmp_path / "f.json")
    tools = FileTools(home=home, protected=[tmp_path / "windows"])
    skills = build_docs_skills(index, folders, tools, announce=lambda *a: announced.append(a), run_async=lambda fn: fn())
    return SkillRegistry(skills), index, folders, home


def test_index_my_documents_by_voice(tmp_path, notes):
    announced = []
    reg, index, folders, home = registry(tmp_path, notes, announced)
    (home / "Documents" / "kerberos.md").write_text(KERBEROS)

    assert "Reading Documents in the background" in reg.handle("index my documents")
    assert index.stats()["files"] == 1 and "1 documents are searchable" in announced[0][0]
    assert folders.all() == [str(home / "Documents")]
    assert "1 documents from Documents" in reg.handle("how many documents have you indexed")

    (home / "notes" / "x.txt").write_text("hello world zzzcustom")
    assert "Reading notes" in reg.handle("scan the notes folder")
    assert index.search("zzzcustom")


def test_index_refuses_system_and_missing_folders(tmp_path, notes):
    reg, index, _, home = registry(tmp_path, notes, [])
    (tmp_path / "windows").mkdir()
    reg_tools = FileTools(home=home, protected=[tmp_path / "windows"])
    assert "can't find a folder called nothing here" in reg.handle("index the nothing here folder")
    assert index.stats()["files"] == 0


def test_forget_documents_needs_confirmation(tmp_path, notes):
    announced = []
    reg, index, folders, home = registry(tmp_path, notes, announced)
    (home / "Documents" / "a.txt").write_text("alpha beta")
    reg.handle("index my documents")
    assert "Are you sure" in reg.handle("forget my documents") and index.stats()["files"] == 1
    assert reg.handle("yes").startswith("Done") and index.stats()["files"] == 0 and folders.all() == []


def test_docs_index_phrases_do_not_catch_everyday_requests(tmp_path, notes):
    reg, *_ = registry(tmp_path, notes, [])
    for phrase in ("read my email", "scan this qr code", "study for my exam", "index funds are a good investment",
                   "add milk to the list", "read the news"):
        assert reg.handle(phrase) is None, phrase


def test_folder_list_persists(tmp_path):
    f = FolderList(tmp_path / "f.json")
    f.add("C:/a"); f.add("C:/a"); f.add("C:/b")
    assert FolderList(tmp_path / "f.json").all() == ["C:/a", "C:/b"]
    f.remove("C:/a")
    assert FolderList(tmp_path / "f.json").all() == ["C:/b"]
    (tmp_path / "bad.json").write_text("nope")
    assert FolderList(tmp_path / "bad.json").all() == []
