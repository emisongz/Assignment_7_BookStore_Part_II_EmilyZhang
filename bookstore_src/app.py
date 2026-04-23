from flask import Flask, render_template, request, redirect, url_for
import os
import sqlite3

app = Flask(__name__)
DATABASE = "bookstore.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # SQLite normally gives us rows as tuples, where we access values by position (row[2])
                                    # The row factory lets us access values by column name instead (row["title"] or {{ row.title }})
    return conn


# ----------------------------------------------------------------------
# Sort helper: translates a ?sort= query-string value into a safe SQL
# ORDER BY clause. We can't just interpolate user input into SQL, so we
# whitelist the allowed values and map each to a known-good snippet.
# ----------------------------------------------------------------------
SORT_OPTIONS = {
    "title-asc":   "title COLLATE NOCASE ASC",
    "title-desc":  "title COLLATE NOCASE DESC",
    "price-asc":   "price ASC",
    "price-desc":  "price DESC",
    "author-asc":  "author COLLATE NOCASE ASC",
}

def resolve_sort(value):
    """Return a safe ORDER BY fragment, defaulting to title-asc."""
    return SORT_OPTIONS.get(value, SORT_OPTIONS["title-asc"])


@app.route("/", methods=["GET"])
def home():
    conn = get_db_connection()

    categories = conn.execute("""
        SELECT *
        FROM category
        ORDER BY categoryName
    """).fetchall()

    # ------------------------------------------------------------------
    # Feature: Featured Book
    # Pick one random book (joined with its category) to highlight on
    # the home page every time the page loads.
    # ------------------------------------------------------------------
    featured = conn.execute("""
        SELECT book.*, category.categoryName
        FROM book
        JOIN category ON book.categoryId = category.categoryId
        ORDER BY RANDOM()
        LIMIT 1
    """).fetchone()

    conn.close()

    return render_template(
        "index.html",
        categories=categories,
        featured=featured
    )


@app.route("/category", methods=["GET"])
def category():
    category_id = request.args.get("categoryId", type=int)
    sort_key    = request.args.get("sort", "title-asc")
    read_now    = request.args.get("readNow")  # "1" when the filter is on
    order_by    = resolve_sort(sort_key)

    conn = get_db_connection()

    categories = conn.execute("""
        SELECT *
        FROM category
        ORDER BY categoryName
    """).fetchall()

    selected_category = conn.execute("""
        SELECT *
        FROM category
        WHERE categoryId = ?
    """, (category_id,)).fetchone()

    # ------------------------------------------------------------------
    # Feature: Sort + Filter by readNow
    # Build the WHERE clause dynamically so we can optionally add the
    # readNow = 1 filter on top of the categoryId match.
    # ------------------------------------------------------------------
    where_clauses = ["categoryId = ?"]
    params = [category_id]

    if read_now == "1":
        where_clauses.append("readNow = 1")

    books_query = f"""
        SELECT *
        FROM book
        WHERE {' AND '.join(where_clauses)}
        ORDER BY {order_by}
    """
    books = conn.execute(books_query, params).fetchall()

    conn.close()

    return render_template(
        "category.html",
        categories=categories,
        selectedCategory=selected_category,
        books=books,
        searchTerm=None,
        nothingFound=False,
        sortKey=sort_key,
        readNowFilter=(read_now == "1"),
    )


@app.route("/search", methods=["POST", "GET"])
def search():
    # Accept both POST (from the search bar) and GET (so sort/filter
    # links on the results page can reuse the same route).
    if request.method == "POST":
        term = request.form.get("search", "").strip()
    else:
        term = request.args.get("search", "").strip()

    sort_key = request.args.get("sort", "title-asc")
    read_now = request.args.get("readNow")
    order_by = resolve_sort(sort_key)

    conn = get_db_connection()

    categories = conn.execute("""
        SELECT *
        FROM category
        ORDER BY categoryName
    """).fetchall()

    where_clauses = ["lower(title) LIKE lower(?)"]
    params = [f"%{term}%"]

    if read_now == "1":
        where_clauses.append("readNow = 1")

    books_query = f"""
        SELECT *
        FROM book
        WHERE {' AND '.join(where_clauses)}
        ORDER BY {order_by}
    """
    books = conn.execute(books_query, params).fetchall()

    conn.close()

    return render_template(
        "category.html",
        categories=categories,
        selectedCategory=None,
        books=books,
        searchTerm=term,
        nothingFound=(len(books) == 0),
        sortKey=sort_key,
        readNowFilter=(read_now == "1"),
    )


@app.route("/book", methods=["GET"])
def book_detail():
    book_id = request.args.get("bookId", type=int)

    conn = get_db_connection()

    categories = conn.execute("""
        SELECT * FROM category ORDER BY categoryName
    """).fetchall()

    book = conn.execute("""
        SELECT book.*, category.categoryName
        FROM book
        JOIN category ON book.categoryId = category.categoryId
        WHERE book.bookId = ?
    """, (book_id,)).fetchone()

    conn.close()

    return render_template(
        "book_detail.html",
        book=book,
        categories=categories
    )


# ----------------------------------------------------------------------
# Feature: Show books by author
# Takes an author name on the query string and lists every book we have
# by that author (sortable via the same sort keys as /category).
# ----------------------------------------------------------------------
@app.route("/author", methods=["GET"])
def author():
    name = request.args.get("name", "").strip()
    sort_key = request.args.get("sort", "title-asc")
    order_by = resolve_sort(sort_key)

    conn = get_db_connection()

    categories = conn.execute("""
        SELECT * FROM category ORDER BY categoryName
    """).fetchall()

    books = conn.execute(f"""
        SELECT book.*, category.categoryName
        FROM book
        JOIN category ON book.categoryId = category.categoryId
        WHERE book.author = ?
        ORDER BY {order_by}
    """, (name,)).fetchall()

    conn.close()

    return render_template(
        "author.html",
        categories=categories,
        authorName=name,
        books=books,
        sortKey=sort_key,
    )


# ----------------------------------------------------------------------
# Feature: Read Now shelf
# A dedicated page that lists every book flagged readNow = 1, regardless
# of category. Reached from the Read Now badge anywhere in the site.
# ----------------------------------------------------------------------
@app.route("/read-now", methods=["GET"])
def read_now():
    sort_key = request.args.get("sort", "title-asc")
    order_by = resolve_sort(sort_key)

    conn = get_db_connection()

    categories = conn.execute("""
        SELECT * FROM category ORDER BY categoryName
    """).fetchall()

    books = conn.execute(f"""
        SELECT book.*, category.categoryName
        FROM book
        JOIN category ON book.categoryId = category.categoryId
        WHERE book.readNow = 1
        ORDER BY {order_by}
    """).fetchall()

    conn.close()

    return render_template(
        "read_now.html",
        categories=categories,
        books=books,
        sortKey=sort_key,
    )


@app.route("/add-book", methods=["GET", "POST"])
def add_book():
    conn = get_db_connection()

    categories = conn.execute("""
        SELECT * FROM category ORDER BY categoryName
    """).fetchall()

    if request.method == "POST":
        title = request.form.get("title")
        author = request.form.get("author")
        isbn = request.form.get("isbn")
        price = request.form.get("price", type=float)
        image = request.form.get("image")
        category_id = request.form.get("categoryId", type=int)
        read_now = 1 if request.form.get("readNow") else 0

        conn.execute("""
            INSERT INTO book (categoryId, title, author, isbn, price, image, readNow)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (category_id, title, author, isbn, price, image, read_now))

        conn.commit()
        conn.close()

        return redirect(url_for("home"))

    conn.close()
    return render_template("add_book.html", categories=categories)


# ----------------------------------------------------------------------
# Additional feature: Edit Book page
# Loads an existing book by bookId, shows a prefilled form on GET,
# and UPDATEs the book record on POST.
# ----------------------------------------------------------------------
@app.route("/edit-book", methods=["GET", "POST"])
def edit_book():
    book_id = request.args.get("bookId", type=int)

    conn = get_db_connection()

    categories = conn.execute("""
        SELECT * FROM category ORDER BY categoryName
    """).fetchall()

    if request.method == "POST":
        title = request.form.get("title")
        author = request.form.get("author")
        isbn = request.form.get("isbn")
        price = request.form.get("price", type=float)
        image = request.form.get("image")
        category_id = request.form.get("categoryId", type=int)
        read_now = 1 if request.form.get("readNow") else 0

        conn.execute("""
            UPDATE book
            SET categoryId = ?,
                title = ?,
                author = ?,
                isbn = ?,
                price = ?,
                image = ?,
                readNow = ?
            WHERE bookId = ?
        """, (category_id, title, author, isbn, price, image, read_now, book_id))

        conn.commit()
        conn.close()

        return redirect(url_for("book_detail", bookId=book_id))

    # GET: load the book and show the prefilled form
    book = conn.execute("""
        SELECT * FROM book WHERE bookId = ?
    """, (book_id,)).fetchone()

    conn.close()

    return render_template(
        "edit_book.html",
        book=book,
        categories=categories
    )


@app.errorhandler(Exception)
def handle_error(e):
    return render_template("error.html", error=e), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)