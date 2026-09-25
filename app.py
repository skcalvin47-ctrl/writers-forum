from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from functools import wraps
from datetime import datetime
from sqlalchemy import or_
import os

from models import (
    db, User, Genre, Book, Chapter, Club,
    Like, Rating, View, Save, Share, Follow, Report
)

STAR_POINTS = {1: 0.2, 2: 0.5, 3: 2, 4: 2.5, 5: 3}
GRACE_HOURS = 72  # 2-4 day grace window for new books


def recompute_rank(book):
    """Recalculate a book's rank_score from its like/dislike ratio and rating,
    applying a decaying grace boost for brand-new books."""
    total_reactions = book.like_count + book.dislike_count
    ratio = (book.like_count / total_reactions) if total_reactions > 0 else 1.0
    rating_factor = (book.avg_rating / 5) if book.avg_rating else 1.0
    base_score = ratio * rating_factor

    age_hours = (datetime.utcnow() - book.created_at).total_seconds() / 3600
    if age_hours < GRACE_HOURS:
        grace_factor = 1 - (age_hours / GRACE_HOURS)
        book.rank_score = base_score + (1 - base_score) * grace_factor
    else:
        book.rank_score = base_score


def recompute_avg_rating(book):
    ratings = Rating.query.filter_by(book_id=book.id).all()
    if ratings:
        book.avg_rating = sum(r.stars for r in ratings) / len(ratings)
    else:
        book.avg_rating = 0

mail = Mail()


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'change-this-to-a-random-secret-key'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///writers_forum.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # ---- Mail config: values loaded from .env, never hardcoded ----
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')

    mail.init_app(app)
    db.init_app(app)
    app.serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

    with app.app_context():
        db.create_all()
        seed_genres()

    register_routes(app)
    return app


def seed_genres():
    """Populate default genres if the table is empty."""
    if Genre.query.count() == 0:
        defaults = ['Action', 'Romance', 'Adventure', 'Anime', 'Animated', 'Fantasy', 'Drama']
        for name in defaults:
            db.session.add(Genre(name=name, slug=name.lower()))
        db.session.commit()


# ---------- AUTH HELPERS ----------

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            user = User.query.get(session['user_id'])
            if user.role not in roles:
                flash("You don't have permission to do that.", 'error')
                return redirect(url_for('home'))
            return f(*args, **kwargs)
        return wrapper
    return decorator


def current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None


# ---------- ROUTES ----------

def register_routes(app):

    @app.context_processor
    def inject_user():
        return dict(current_user=current_user())

    @app.route('/')
    def home():
        featured = Book.query.filter_by(status='approved').order_by(Book.rank_score.desc()).limit(6).all()
        top_rated = Book.query.filter_by(status='approved').order_by(Book.avg_rating.desc()).limit(10).all()
        latest = Book.query.filter_by(status='approved').order_by(Book.created_at.desc()).limit(10).all()
        genres = Genre.query.all()
        return render_template('home.html', featured=featured, top_rated=top_rated,
                                latest=latest, genres=genres)

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            username = request.form['username'].strip()
            email = request.form['email'].strip().lower()
            password = request.form['password']

            if User.query.filter((User.username == username) | (User.email == email)).first():
                flash('Username or email already taken.', 'error')
                return redirect(url_for('register'))

            chosen_role = request.form.get('role', 'reader')
            if chosen_role not in ('reader', 'writer'):
                chosen_role = 'reader'

            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
                role=chosen_role,
                confirmed=False
            )
            db.session.add(user)
            db.session.commit()

            token = app.serializer.dumps(email, salt='email-confirm')
            confirm_url = url_for('confirm_email', token=token, _external=True)

            msg = Message('Confirm your Writer\'s Forum account', recipients=[email])
            msg.body = f'Welcome to Writer\'s Forum! Click to confirm your account: {confirm_url}'
            mail.send(msg)

            flash('Account created! Check your email to confirm before logging in.', 'success')
            return redirect(url_for('login'))

        return render_template('register.html')

    @app.route('/confirm/<token>')
    def confirm_email(token):
        try:
            email = app.serializer.loads(token, salt='email-confirm', max_age=3600)
        except Exception:
            flash('The confirmation link is invalid or has expired.', 'error')
            return redirect(url_for('login'))

        user = User.query.filter_by(email=email).first()
        if user is None:
            flash('Account not found.', 'error')
        elif user.confirmed:
            flash('Account already confirmed. Please log in.', 'success')
        else:
            user.confirmed = True
            db.session.commit()
            flash('Account confirmed! You can now log in.', 'success')

        return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            email = request.form['email'].strip().lower()
            password = request.form['password']

            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                if not user.confirmed:
                    flash('Please confirm your email before logging in.', 'error')
                    return redirect(url_for('login'))
                session['user_id'] = user.id
                flash(f'Welcome back, {user.username}!', 'success')
                return redirect(url_for('home'))

            flash('Invalid email or password.', 'error')
            return redirect(url_for('login'))

        return render_template('login.html')

    @app.route('/logout')
    def logout():
        session.pop('user_id', None)
        flash('Logged out.', 'success')
        return redirect(url_for('home'))

    @app.route('/points')
    def points_info():
        return render_template('points_info.html')

    @app.route('/terms')
    def terms():
        return render_template('terms.html')

    @app.route('/search')
    def search():
        query = request.args.get('q', '').strip()
        results = []
        if query:
            like_term = f'%{query}%'
            results = Book.query.filter(
                Book.status == 'approved',
                or_(Book.title.ilike(like_term), Book.description.ilike(like_term))
            ).order_by(Book.rank_score.desc()).all()

            author_matches = Book.query.join(User, Book.author_id == User.id).filter(
                Book.status == 'approved',
                User.username.ilike(like_term)
            ).all()
            for b in author_matches:
                if b not in results:
                    results.append(b)

        return render_template('search_results.html', query=query, results=results)

    @app.route('/genre/<slug>')
    def genre_page(slug):
        genre = Genre.query.filter_by(slug=slug).first_or_404()
        books = Book.query.filter_by(genre_id=genre.id, status='approved').order_by(Book.rank_score.desc()).all()
        return render_template('genre.html', genre=genre, books=books)

    @app.route('/book/<int:book_id>')
    def book_preview(book_id):
        book = Book.query.get_or_404(book_id)
        return render_template('book_preview.html', book=book)

    @app.route('/book/<int:book_id>/like', methods=['POST'])
    @login_required
    def like_book(book_id):
        book = Book.query.get_or_404(book_id)
        user = current_user()
        existing = Like.query.filter_by(user_id=user.id, book_id=book.id).first()

        if existing and not existing.is_dislike:
            # already liked -> toggle off
            db.session.delete(existing)
            book.like_count = max(0, book.like_count - 1)
            book.author.forum_points = max(0, book.author.forum_points - 2)
        else:
            if existing and existing.is_dislike:
                db.session.delete(existing)
                book.dislike_count = max(0, book.dislike_count - 1)
            db.session.add(Like(user_id=user.id, book_id=book.id, is_dislike=False))
            book.like_count += 1
            book.author.forum_points += 2

        recompute_rank(book)
        db.session.commit()
        return redirect(url_for('book_preview', book_id=book.id))

    @app.route('/book/<int:book_id>/dislike', methods=['POST'])
    @login_required
    def dislike_book(book_id):
        book = Book.query.get_or_404(book_id)
        user = current_user()
        existing = Like.query.filter_by(user_id=user.id, book_id=book.id).first()

        if existing and existing.is_dislike:
            db.session.delete(existing)
            book.dislike_count = max(0, book.dislike_count - 1)
        else:
            if existing and not existing.is_dislike:
                db.session.delete(existing)
                book.like_count = max(0, book.like_count - 1)
                book.author.forum_points = max(0, book.author.forum_points - 2)
            db.session.add(Like(user_id=user.id, book_id=book.id, is_dislike=True))
            book.dislike_count += 1

        recompute_rank(book)
        db.session.commit()
        return redirect(url_for('book_preview', book_id=book.id))

    @app.route('/book/<int:book_id>/rate', methods=['POST'])
    @login_required
    def rate_book(book_id):
        book = Book.query.get_or_404(book_id)
        user = current_user()
        stars = int(request.form.get('stars', 0))

        if stars not in STAR_POINTS:
            flash('Invalid rating.', 'error')
            return redirect(url_for('book_preview', book_id=book.id))

        existing = Rating.query.filter_by(user_id=user.id, book_id=book.id).first()
        if existing:
            book.author.forum_points = max(0, book.author.forum_points - STAR_POINTS[existing.stars])
            existing.stars = stars
        else:
            db.session.add(Rating(user_id=user.id, book_id=book.id, stars=stars))

        book.author.forum_points += STAR_POINTS[stars]
        recompute_avg_rating(book)
        recompute_rank(book)
        db.session.commit()
        flash('Rating submitted.', 'success')
        return redirect(url_for('book_preview', book_id=book.id))

    @app.route('/book/<int:book_id>/save', methods=['POST'])
    @login_required
    def save_book(book_id):
        book = Book.query.get_or_404(book_id)
        user = current_user()
        existing = Save.query.filter_by(user_id=user.id, book_id=book.id).first()

        if existing:
            db.session.delete(existing)
            book.save_count = max(0, book.save_count - 1)
            flash('Removed from your library.', 'success')
        else:
            db.session.add(Save(user_id=user.id, book_id=book.id))
            book.save_count += 1
            book.author.forum_points += 10
            flash('Saved to your library.', 'success')

        db.session.commit()
        return redirect(url_for('book_preview', book_id=book.id))

    @app.route('/book/<int:book_id>/share', methods=['POST'])
    @login_required
    def share_book(book_id):
        book = Book.query.get_or_404(book_id)
        user = current_user()

        db.session.add(Share(user_id=user.id, book_id=book.id))
        if user.id == book.author_id:
            book.author.forum_points += 8
        else:
            book.author.forum_points += 15
        db.session.commit()
        flash('Book shared!', 'success')
        return redirect(url_for('book_preview', book_id=book.id))

    @app.route('/writer/<int:writer_id>/follow', methods=['POST'])
    @login_required
    def follow_writer(writer_id):
        writer = User.query.get_or_404(writer_id)
        user = current_user()

        if writer.id == user.id:
            flash("You can't follow yourself.", 'error')
            return redirect(url_for('book_preview', book_id=request.form.get('book_id', 0)))

        existing = Follow.query.filter_by(follower_id=user.id, writer_id=writer.id).first()
        if existing:
            db.session.delete(existing)
            flash(f'Unfollowed {writer.username}.', 'success')
        else:
            db.session.add(Follow(follower_id=user.id, writer_id=writer.id))
            writer.forum_points += 5
            flash(f'Now following {writer.username}.', 'success')

        db.session.commit()
        book_id = request.form.get('book_id')
        if book_id:
            return redirect(url_for('book_preview', book_id=book_id))
        return redirect(url_for('home'))

    @app.route('/book/<int:book_id>/report', methods=['GET', 'POST'])
    @login_required
    def report_book(book_id):
        book = Book.query.get_or_404(book_id)

        if request.method == 'POST':
            reason = request.form.get('reason')
            details = request.form.get('details', '').strip()

            db.session.add(Report(
                reporter_id=current_user().id,
                book_id=book.id,
                reason=reason,
                details=details
            ))
            db.session.commit()
            flash('Thanks — this book has been reported to the moderation team.', 'success')
            return redirect(url_for('book_preview', book_id=book.id))

        return render_template('report_book.html', book=book)

    @app.route('/admin/reports')
    @role_required('admin')
    def admin_reports():
        reports = Report.query.filter_by(status='open').order_by(Report.created_at.asc()).all()
        return render_template('admin_reports.html', reports=reports)

    @app.route('/admin/reports/<int:report_id>/dismiss', methods=['POST'])
    @role_required('admin')
    def dismiss_report(report_id):
        report = Report.query.get_or_404(report_id)
        report.status = 'dismissed'
        db.session.commit()
        flash('Report dismissed.', 'success')
        return redirect(url_for('admin_reports'))

    @app.route('/admin/reports/<int:report_id>/remove-book', methods=['POST'])
    @role_required('admin')
    def resolve_report_remove_book(report_id):
        report = Report.query.get_or_404(report_id)
        report.book.status = 'rejected'
        report.status = 'resolved'
        db.session.commit()
        flash('Book removed and report resolved.', 'success')
        return redirect(url_for('admin_reports'))

    @app.route('/read/<int:book_id>/<int:chapter_number>')
    def read_chapter(book_id, chapter_number):
        book = Book.query.get_or_404(book_id)
        chapter = Chapter.query.filter_by(book_id=book.id, chapter_number=chapter_number).first_or_404()
        total_chapters = len(book.chapters)
        is_last = chapter_number >= total_chapters

        user = current_user()
        db.session.add(View(
            user_id=user.id if user else None,
            book_id=book.id,
            completed=is_last
        ))
        book.view_count += 1
        book.author.forum_points += 1 if is_last else 0.8
        recompute_rank(book)
        db.session.commit()

        return render_template(
            'reader.html',
            book=book,
            chapter=chapter,
            chapter_number=chapter_number,
            total_chapters=total_chapters,
            is_last=is_last
        )

    @app.route('/clubs')
    def clubs_list():
        clubs = Club.query.all()
        return render_template('clubs_list.html', clubs=clubs)

    @app.route('/clubs/new', methods=['GET', 'POST'])
    @role_required('writer', 'admin')
    def new_club():
        user = current_user()
        if user.club_id:
            flash("You're already in a club — leave it first to create a new one.", 'error')
            return redirect(url_for('clubs_list'))

        if request.method == 'POST':
            name = request.form['name'].strip()
            description = request.form.get('description', '').strip()

            if Club.query.filter_by(name=name).first():
                flash('A club with that name already exists.', 'error')
                return redirect(url_for('new_club'))

            club = Club(name=name, description=description, founder_id=user.id)
            db.session.add(club)
            db.session.commit()

            user.club_id = club.id
            user.is_board_member = True
            db.session.commit()

            flash(f'Club "{name}" created!', 'success')
            return redirect(url_for('club_profile', club_id=club.id))

        return render_template('new_club.html')

    @app.route('/clubs/<int:club_id>')
    def club_profile(club_id):
        club = Club.query.get_or_404(club_id)
        total_points = sum(m.forum_points for m in club.members)
        return render_template('club_profile.html', club=club, total_points=total_points)

    @app.route('/clubs/<int:club_id>/join', methods=['POST'])
    @role_required('writer', 'admin')
    def join_club(club_id):
        club = Club.query.get_or_404(club_id)
        user = current_user()

        if user.club_id:
            flash("You're already in a club — leave it first.", 'error')
            return redirect(url_for('club_profile', club_id=club.id))

        user.club_id = club.id
        db.session.commit()
        flash(f'You joined {club.name}!', 'success')
        return redirect(url_for('club_profile', club_id=club.id))

    @app.route('/clubs/<int:club_id>/leave', methods=['POST'])
    @login_required
    def leave_club(club_id):
        user = current_user()
        club = Club.query.get_or_404(club_id)

        if user.club_id != club.id:
            flash("You're not a member of that club.", 'error')
            return redirect(url_for('clubs_list'))

        user.club_id = None
        user.is_board_member = False
        db.session.commit()
        flash(f'You left {club.name}.', 'success')
        return redirect(url_for('clubs_list'))

    @app.route('/leaderboard')
    def leaderboard():
        clubs = Club.query.all()
        ranked = sorted(clubs, key=lambda c: sum(m.forum_points for m in c.members), reverse=True)
        ranked_with_points = [(c, sum(m.forum_points for m in c.members)) for c in ranked]
        return render_template('leaderboard.html', ranked_clubs=ranked_with_points)

    @app.route('/write/new', methods=['GET', 'POST'])
    @role_required('writer', 'admin')
    def new_book():
        genres = Genre.query.all()

        if request.method == 'POST':
            title = request.form['title'].strip()
            description = request.form['description'].strip()
            genre_id = request.form['genre_id']
            is_ai_assisted = 'is_ai_assisted' in request.form

            if not title or not genre_id:
                flash('Title and genre are required.', 'error')
                return redirect(url_for('new_book'))

            book = Book(
                title=title,
                description=description,
                genre_id=genre_id,
                author_id=current_user().id,
                is_ai_assisted=is_ai_assisted,
                status='pending'
            )
            db.session.add(book)
            db.session.commit()

            flash('Book created! Now add your first chapter.', 'success')
            return redirect(url_for('add_chapter', book_id=book.id))

        return render_template('new_book.html', genres=genres)

    @app.route('/write/<int:book_id>/chapter/new', methods=['GET', 'POST'])
    @role_required('writer', 'admin')
    def add_chapter(book_id):
        book = Book.query.get_or_404(book_id)

        if book.author_id != current_user().id and current_user().role != 'admin':
            flash("You can't edit someone else's book.", 'error')
            return redirect(url_for('home'))

        if request.method == 'POST':
            chapter_title = request.form.get('chapter_title', '').strip()
            content = request.form['content'].strip()

            if not content:
                flash('Chapter content cannot be empty.', 'error')
                return redirect(url_for('add_chapter', book_id=book.id))

            next_number = len(book.chapters) + 1
            chapter = Chapter(
                book_id=book.id,
                chapter_number=next_number,
                title=chapter_title,
                content=content
            )
            db.session.add(chapter)
            db.session.commit()

            flash(f'Chapter {next_number} added.', 'success')
            return redirect(url_for('add_chapter', book_id=book.id))

        return render_template('add_chapter.html', book=book)

    @app.route('/write/new', methods=['GET', 'POST'])
    @role_required('writer', 'admin')
    def new_book():
        genres = Genre.query.all()

        if request.method == 'POST':
            title = request.form['title'].strip()
            description = request.form['description'].strip()
            genre_id = request.form['genre_id']
            is_ai_assisted = 'is_ai_assisted' in request.form

            if not title or not genre_id:
                flash('Title and genre are required.', 'error')
                return redirect(url_for('new_book'))

            book = Book(
                title=title,
                description=description,
                genre_id=genre_id,
                author_id=current_user().id,
                is_ai_assisted=is_ai_assisted,
                status='pending'
            )
            db.session.add(book)
            db.session.commit()

            cover_file = request.files.get('cover')
            if cover_file and cover_file.filename:
                ext = cover_file.filename.rsplit('.', 1)[-1].lower()
                if ext in ('jpg', 'jpeg', 'png', 'webp'):
                    filename = f'covers/book_{book.id}.{ext}'
                    save_path = os.path.join(app.static_folder, filename)
                    cover_file.save(save_path)
                    book.cover_image = filename
                    db.session.commit()
                else:
                    flash('Cover must be a JPG, PNG, or WEBP image.', 'error')

            flash('Book created! Now add your first chapter.', 'success')
            return redirect(url_for('add_chapter', book_id=book.id))

        return render_template('new_book.html', genres=genres)
    @app.route('/admin/queue')
    @role_required('admin')
    def admin_queue():
        pending_books = Book.query.filter_by(status='pending').order_by(Book.created_at.asc()).all()
        return render_template('admin_queue.html', books=pending_books)

    @app.route('/admin/approve/<int:book_id>', methods=['POST'])
    @role_required('admin')
    def approve_book(book_id):
        book = Book.query.get_or_404(book_id)
        book.status = 'approved'
        db.session.commit()
        flash(f'"{book.title}" approved and published.', 'success')
        return redirect(url_for('admin_queue'))

    @app.route('/admin/reject/<int:book_id>', methods=['POST'])
    @role_required('admin')
    def reject_book(book_id):
        book = Book.query.get_or_404(book_id)
        book.status = 'rejected'
        db.session.commit()
        flash(f'"{book.title}" rejected.', 'success')
        return redirect(url_for('admin_queue'))


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
