from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# ---------- USERS & ROLES ----------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='reader')  # reader | writer | admin
    bio = db.Column(db.Text)
    avatar = db.Column(db.String(255))
    forum_points = db.Column(db.Float, default=0)
    club_id = db.Column(db.Integer, db.ForeignKey('club.id'), nullable=True)
    is_board_member = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    confirmed = db.Column(db.Boolean, default=False)

    books = db.relationship('Book', backref='author', lazy=True)


# ---------- GENRES & BOOKS ----------

class Genre(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)


class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    cover_image = db.Column(db.String(255))
    description = db.Column(db.Text)
    genre_id = db.Column(db.Integer, db.ForeignKey('genre.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending | approved | rejected
    is_ai_assisted = db.Column(db.Boolean, default=False)
    has_pictures = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    like_count = db.Column(db.Integer, default=0)
    dislike_count = db.Column(db.Integer, default=0)
    view_count = db.Column(db.Integer, default=0)
    save_count = db.Column(db.Integer, default=0)
    avg_rating = db.Column(db.Float, default=0)
    rank_score = db.Column(db.Float, default=0)

    genre = db.relationship('Genre', backref='books')
    chapters = db.relationship('Chapter', backref='book', lazy=True, order_by='Chapter.chapter_number')


class Chapter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    chapter_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200))
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    images = db.relationship('ChapterImage', backref='chapter', lazy=True, order_by='ChapterImage.position')


class ChapterImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapter.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    position = db.Column(db.Integer, default=0)  # order among this chapter's images (0-3, max 4)


# ---------- ENGAGEMENT ----------

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    is_dislike = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    stars = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class View(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User')


class Save(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Share(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    writer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------- MODERATION ----------

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    reason = db.Column(db.String(50), nullable=False)  # plagiarism | explicit | hate_speech | spam | other
    details = db.Column(db.Text)
    status = db.Column(db.String(20), default='open')  # open | resolved | dismissed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    book = db.relationship('Book', backref='reports')
    reporter = db.relationship('User', foreign_keys=[reporter_id])


# ---------- BOOSTS (paid visibility) ----------

class Boost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    boost_type = db.Column(db.String(20))  # homepage_preview | genre_top
    starts_at = db.Column(db.DateTime, default=datetime.utcnow)
    ends_at = db.Column(db.DateTime, nullable=False)


# ---------- CLUBS ----------

class Club(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    banner = db.Column(db.String(255))
    founder_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_points = db.Column(db.Float, default=0)
    transfer_reserve = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    members = db.relationship('User', backref='club', lazy=True, foreign_keys=[User.club_id])


class ClubPoll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey('club.id'), nullable=False)
    poll_type = db.Column(db.String(30))  # dissolve | mvp_reallocation | other
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='open')  # open | passed | failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    closes_at = db.Column(db.DateTime)


class ClubPollVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('club_poll.id'), nullable=False)
    voter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vote = db.Column(db.Boolean)


class Transfer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    writer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    from_club_id = db.Column(db.Integer, db.ForeignKey('club.id'), nullable=True)
    to_club_id = db.Column(db.Integer, db.ForeignKey('club.id'), nullable=False)
    fee = db.Column(db.Float, nullable=False)
    writer_cut = db.Column(db.Float)
    status = db.Column(db.String(20), default='pending')  # pending | accepted | declined
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------- MVP MONTHLY COMPETITION ----------

class MVPCompetition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey('club.id'), nullable=False)
    genre_id = db.Column(db.Integer, db.ForeignKey('genre.id'), nullable=False)
    prize_pool = db.Column(db.Float)
    month = db.Column(db.String(7))  # 'YYYY-MM'
    winner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(db.String(20), default='open')  # open | closed


class MVPEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey('mvp_competition.id'), nullable=False)
    writer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    nominated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
