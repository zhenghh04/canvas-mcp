"""Course content: wiki pages, modules, quizzes, and files."""

from __future__ import annotations

from pathlib import Path

from ..formatting import form, slim, slim_all, strip_html
from ..registry import Registrar

PAGE_KEYS = ("page_id", "url", "title", "published", "front_page", "updated_at", "html_url")
MODULE_KEYS = ("id", "name", "position", "published", "items_count", "unlock_at")
FILE_KEYS = ("id", "display_name", "filename", "content-type", "size", "url", "updated_at")

#: Which identifier each module-item type needs. Canvas 400s unhelpfully when
#: you pick the wrong one, so the tool checks before sending.
ITEM_NEEDS_CONTENT_ID = frozenset({"Assignment", "Quiz", "File", "Discussion"})
ITEM_NEEDS_URL = frozenset({"ExternalUrl", "ExternalTool"})
ITEM_TYPES = (
    "Assignment",
    "Quiz",
    "File",
    "Page",
    "Discussion",
    "SubHeader",
    "ExternalUrl",
    "ExternalTool",
)


def register(reg: Registrar) -> None:
    client = reg.client
    config = reg.config

    # -- pages ------------------------------------------------------------

    @reg.tool(group="content")
    def canvas_list_pages(course_id: str = "", search_term: str = "") -> str:
        """List wiki pages in a course (titles and url slugs, not bodies).

        The ``url`` field is the slug every other page tool wants — not the
        numeric page_id, and not the full browser URL.

        Args:
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
            search_term: optional title substring filter.
        """
        cid = client.course(course_id)
        params = {"search_term": search_term} if search_term else {}
        return client.fmt(slim_all(client.paged(f"courses/{cid}/pages", params), PAGE_KEYS))

    @reg.tool(group="content")
    def canvas_get_page(page_url: str, course_id: str = "", max_chars: int = 0) -> str:
        """Get one wiki page's body as plain text.

        Args:
            page_url: the page's url slug (from canvas_list_pages).
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
            max_chars: bound on the returned payload (0 = the server default).
        """
        cid = client.course(course_id)
        data = client.get_json(f"courses/{cid}/pages/{page_url}")
        data["body"] = strip_html(data.get("body", ""))
        return client.fmt(data, max_chars or None)

    @reg.tool(group="content", tier="write")
    def canvas_create_page(
        title: str,
        body: str = "",
        published: bool = False,
        front_page: bool = False,
        course_id: str = "",
    ) -> str:
        """Create a wiki page. MUTATES the course.

        Defaults to UNPUBLISHED. Canvas derives the page's url slug from the
        title; the returned ``url`` is what canvas_get_page and
        canvas_update_page expect, not the numeric page_id.

        Args:
            title: page title.
            body: page HTML.
            published: visible to students immediately (default False).
            front_page: make this the course home page.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        payload = form(
            **{
                "wiki_page[title]": title,
                "wiki_page[body]": body,
                "wiki_page[published]": published,
                "wiki_page[front_page]": front_page or None,
            }
        )
        data = client.request("POST", f"courses/{cid}/pages", data=payload).json()
        return client.fmt(slim(data, PAGE_KEYS))

    @reg.tool(group="content", tier="write")
    def canvas_update_page(
        page_url: str,
        title: str = "",
        body: str = "",
        published: bool | None = None,
        course_id: str = "",
    ) -> str:
        """Edit a wiki page. MUTATES the course.

        Only the fields you pass change. Passing body REPLACES the whole page —
        read canvas_get_page first if you mean to append. Note that
        canvas_get_page returns plain text, so round-tripping it through this
        tool will flatten the page's existing HTML formatting.

        Args:
            page_url: the page's url slug (from canvas_list_pages), not its id.
            title: new title, or empty to leave unchanged. Renaming does NOT
                change the url slug, so existing links keep working.
            body: new page HTML, or empty to leave unchanged.
            published: True/False to change visibility, or omit to leave alone.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        payload = form(
            **{
                "wiki_page[title]": title,
                "wiki_page[body]": body,
                "wiki_page[published]": published,
            }
        )
        if not payload:
            return "ERROR: no fields given to update — nothing to change."
        data = client.request("PUT", f"courses/{cid}/pages/{page_url}", data=payload).json()
        return client.fmt(slim(data, PAGE_KEYS))

    @reg.tool(group="content", tier="destructive")
    def canvas_delete_page(page_url: str, course_id: str = "") -> str:
        """Delete a wiki page. MUTATES the course.

        Soft-delete — recoverable from the course's /undelete page, but any
        module item or page link pointing at it breaks immediately.

        Args:
            page_url: the page's url slug (from canvas_list_pages).
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        data = client.request("DELETE", f"courses/{cid}/pages/{page_url}").json()
        out = slim(data, ("page_id", "url", "title"))
        out["undelete_url"] = f"{config.base_url}/courses/{cid}/undelete"
        return client.fmt(out)

    # -- modules ----------------------------------------------------------

    @reg.tool(group="content")
    def canvas_list_modules(
        course_id: str = "", with_items: bool = True, max_chars: int = 0
    ) -> str:
        """List course modules, optionally with their items — the course outline.

        This is the fastest way to see how a course is actually structured
        week by week.

        Args:
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
            with_items: inline each module's items (default True).
            max_chars: bound on the returned payload (0 = the server default).
        """
        cid = client.course(course_id)
        params = {"include[]": ["items"]} if with_items else {}
        out = []
        for module in client.paged(f"courses/{cid}/modules", params):
            if not isinstance(module, dict):
                out.append(module)
                continue
            row = slim(module, MODULE_KEYS)
            if with_items:
                row["items"] = [
                    slim(
                        i,
                        ("id", "title", "type", "content_id", "page_url", "published", "html_url"),
                    )
                    for i in module.get("items") or []
                ]
            out.append(row)
        return client.fmt(out, max_chars or None)

    @reg.tool(group="content", tier="write")
    def canvas_create_module(
        name: str, position: int | None = None, published: bool = False, course_id: str = ""
    ) -> str:
        """Create a course module. MUTATES the course.

        A module is an empty container until you add items with
        canvas_create_module_item. Defaults to UNPUBLISHED.

        Args:
            name: module title, e.g. "Week 3 — Coding agents".
            position: 1-based slot in the module list; omit to append at the end.
            published: visible to students immediately (default False).
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        payload = form(
            **{"module[name]": name, "module[position]": position, "module[published]": published}
        )
        data = client.request("POST", f"courses/{cid}/modules", data=payload).json()
        return client.fmt(slim(data, MODULE_KEYS))

    @reg.tool(group="content", tier="write")
    def canvas_update_module(
        module_id: str,
        name: str = "",
        position: int | None = None,
        published: bool | None = None,
        course_id: str = "",
    ) -> str:
        """Edit or publish a module. MUTATES the course.

        Publishing a module publishes its items too, which is the usual way a
        week's content goes live for students. Only the fields you pass change.

        Args:
            module_id: numeric module id.
            name: new title, or empty to leave unchanged.
            position: new 1-based slot, or omit to leave unchanged.
            published: True/False to change visibility, or omit to leave alone.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        payload = form(
            **{"module[name]": name, "module[position]": position, "module[published]": published}
        )
        if not payload:
            return "ERROR: no fields given to update — nothing to change."
        data = client.request("PUT", f"courses/{cid}/modules/{module_id}", data=payload).json()
        return client.fmt(slim(data, MODULE_KEYS))

    @reg.tool(group="content", tier="write")
    def canvas_create_module_item(
        module_id: str,
        title: str,
        item_type: str,
        content_id: str = "",
        page_url: str = "",
        external_url: str = "",
        position: int | None = None,
        indent: int | None = None,
        course_id: str = "",
    ) -> str:
        """Add an item to a module. MUTATES the course.

        Which id field you need depends on item_type:
          Assignment / Quiz / Discussion / File  -> content_id (the object's id)
          Page                                   -> page_url (the slug)
          ExternalUrl / ExternalTool             -> external_url
          SubHeader                              -> neither; title is the item

        Args:
            module_id: numeric module id.
            title: item label shown in the module list.
            item_type: one of Assignment, Quiz, File, Page, Discussion,
                SubHeader, ExternalUrl, ExternalTool.
            content_id: id of the linked object, for the types that need one.
            page_url: page slug, for item_type=Page.
            external_url: target, for item_type=ExternalUrl or ExternalTool.
            position: 1-based slot within the module; omit to append.
            indent: nesting level, 0 for top level.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        if item_type not in ITEM_TYPES:
            return f"ERROR: item_type must be one of {list(ITEM_TYPES)}, got {item_type!r}."
        if item_type in ITEM_NEEDS_CONTENT_ID and not content_id:
            return (
                f"ERROR: item_type={item_type} requires content_id (the numeric id of the "
                "assignment/quiz/file/discussion to link)."
            )
        if item_type == "Page" and not page_url:
            return (
                "ERROR: item_type=Page requires page_url (the slug from canvas_list_pages), "
                "not content_id."
            )
        if item_type in ITEM_NEEDS_URL and not external_url:
            return f"ERROR: item_type={item_type} requires external_url."
        cid = client.course(course_id)
        payload = form(
            **{
                "module_item[title]": title,
                "module_item[type]": item_type,
                "module_item[content_id]": content_id,
                "module_item[page_url]": page_url,
                "module_item[external_url]": external_url,
                "module_item[position]": position,
                "module_item[indent]": indent,
            }
        )
        data = client.request(
            "POST", f"courses/{cid}/modules/{module_id}/items", data=payload
        ).json()
        return client.fmt(slim(data, ("id", "title", "type", "position", "indent", "html_url")))

    @reg.tool(group="content", tier="destructive")
    def canvas_delete_module(module_id: str, course_id: str = "") -> str:
        """Delete a module. MUTATES the course.

        Removes the module and its item links. The underlying assignments and
        pages survive — only their placement in the module is lost.

        Args:
            module_id: numeric module id.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        data = client.request("DELETE", f"courses/{cid}/modules/{module_id}").json()
        return client.fmt(slim(data, ("id", "name", "workflow_state")))

    # -- quizzes ----------------------------------------------------------

    @reg.tool(group="content")
    def canvas_list_quizzes(course_id: str = "") -> str:
        """List quizzes in a course.

        Note: this covers Classic Quizzes. Institutions on New Quizzes see them
        as assignments with submission_type=external_tool instead — check
        canvas_list_assignments if a quiz you expect is missing here.

        Args:
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        keys = ("id", "title", "quiz_type", "due_at", "points_possible", "published", "html_url")
        return client.fmt(slim_all(client.paged(f"courses/{cid}/quizzes"), keys))

    # -- files ------------------------------------------------------------

    @reg.tool(group="content")
    def canvas_list_files(course_id: str = "", search_term: str = "") -> str:
        """List files uploaded to a course.

        Args:
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
            search_term: optional filename substring filter (3+ characters).
        """
        cid = client.course(course_id)
        params = {"search_term": search_term} if search_term else {}
        return client.fmt(slim_all(client.paged(f"courses/{cid}/files", params), FILE_KEYS))

    @reg.tool(group="content")
    def canvas_download_file(file_id: str, dest_dir: str = "", name: str = "") -> str:
        """Download one course file to local disk.

        Writes to the machine running this server, not the user's laptop, if
        those differ.

        Args:
            file_id: numeric file id (from canvas_list_files).
            dest_dir: destination folder; defaults to CANVAS_DOWNLOAD_DIR, or
                ./canvas-downloads.
            name: filename to save as; defaults to the Canvas display name.
        """
        meta = client.get_json(f"files/{file_id}")
        url = meta.get("url")
        if not url:
            return (
                f"ERROR: file {file_id} has no download url — it may be locked, in the "
                "recycle bin, or stored by a tool that does not expose a direct link."
            )
        root = Path(dest_dir).expanduser() if dest_dir else client.config.downloads_path()
        dest = root / (name or meta.get("display_name") or f"canvas-{file_id}")
        size = client.download(url, dest)
        return client.fmt({"file_id": file_id, "path": str(dest), "bytes": size})

    @reg.tool(group="content", tier="write")
    def canvas_upload_file(
        local_path: str,
        parent_folder_path: str = "course files",
        name: str = "",
        on_duplicate: str = "rename",
        course_id: str = "",
    ) -> str:
        """Upload a local file into the course's Files area. MUTATES the course.

        Three-step Canvas dance, handled here: register the upload, POST the
        bytes to the storage host, then confirm. The Canvas token is never sent
        to the storage host.

        Args:
            local_path: absolute path to the file on the machine running this
                server.
            parent_folder_path: Canvas folder, e.g. "course files/week03".
                Created if it does not exist.
            name: name to store it under; defaults to the local filename.
            on_duplicate: "rename" (default, keeps both) or "overwrite".
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        if on_duplicate not in {"rename", "overwrite"}:
            return f"ERROR: on_duplicate must be 'rename' or 'overwrite', got {on_duplicate!r}."
        path = Path(local_path).expanduser()
        if not path.is_file():
            return f"ERROR: no such file: {path}"
        size = path.stat().st_size
        cap = config.max_upload_mb
        if size > cap * 1024 * 1024:
            return (
                f"ERROR: {path.name} is {size / 1048576:.1f} MB, over the {cap} MB cap this "
                "tool enforces. Raise CANVAS_MAX_UPLOAD_MB if your Canvas quota allows it."
            )
        cid = client.course(course_id)
        data = client.upload_file(cid, path, name or path.name, parent_folder_path, on_duplicate)
        out = slim(data, FILE_KEYS)
        out["html_url"] = f"{config.base_url}/courses/{cid}/files/{data.get('id')}"
        return client.fmt(out)
