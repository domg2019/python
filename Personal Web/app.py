from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////opt/myapp/tickets.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'  # 必须设置且保密！

# 初始化扩展
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# ----------------- 数据库模型 -----------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    tickets = db.relationship('Ticket', backref='category', lazy=True)


class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(200), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.relationship('TicketDetail', backref='ticket', lazy=True, cascade='all, delete-orphan')


class TicketDetail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    field_name = db.Column(db.String(50), nullable=False)
    field_value = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# ----------------- 表单类 -----------------
class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    password = PasswordField('密码', validators=[DataRequired()])
    submit = SubmitField('登录')


class RegistrationForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(min=4, max=20)])
    email = StringField('邮箱', validators=[DataRequired(), Email()])
    password = PasswordField('密码', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('注册')


# ----------------- 认证相关路由 -----------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for('index'))
        flash('无效的用户名或密码')
    return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        existing_user = User.query.filter_by(username=form.username.data).first()
        if existing_user:
            flash('用户名已存在')
            return redirect(url_for('register'))

        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('注册成功，请登录')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)


# ----------------- 受保护的路由 -----------------
@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        # 处理分类添加
        if 'new_category' in request.form:
            new_category = request.form['new_category']
            if not Category.query.filter_by(name=new_category).first():
                db.session.add(Category(name=new_category))
                db.session.commit()
                flash('分类添加成功')
            else:
                flash('分类已存在')
            return redirect(url_for('index'))

        # 处理Ticket添加
        elif 'ticket_content' in request.form:
            content = request.form['ticket_content']
            category_id = request.form['category_id']
            # 检查是否已存在相同的 Ticket
            existing_ticket = Ticket.query.filter_by(content=content, category_id=category_id).first()
            if not existing_ticket and content.strip():  # 检查内容是否为空且不重复
                db.session.add(Ticket(content=content, category_id=category_id))
                db.session.commit()
                flash('Ticket添加成功')
            else:
                flash('Ticket已存在或内容为空')
            return redirect(url_for('index'))

    categories = Category.query.all()
    return render_template('index.html', categories=categories)

@app.route('/delete/<int:ticket_id>')
@login_required
def delete_ticket(ticket_id):
    ticket = Ticket.query.get(ticket_id)
    if ticket:
        db.session.delete(ticket)
        db.session.commit()
    return redirect(url_for('index'))


@app.route('/delete_category/<int:category_id>')
@login_required
def delete_category(category_id):
    category = Category.query.get(category_id)
    if category:
        # 先删除关联的 Tickets
        Ticket.query.filter_by(category_id=category_id).delete()
        # 再删除分类
        db.session.delete(category)
        db.session.commit()
    return redirect(url_for('index'))


@app.route('/add_detail/<int:ticket_id>', methods=['POST'])
@login_required
def add_detail(ticket_id):
    ticket = Ticket.query.get(ticket_id)
    if ticket:
        field_name = request.form.get('field_name')
        field_value = request.form.get('field_value')
        if field_name and field_value:
            detail = TicketDetail(
                ticket_id=ticket_id,
                field_name=field_name,
                field_value=field_value
            )
            db.session.add(detail)
            db.session.commit()
            return jsonify({
                'status': 'success',
                'detail': {
                    'id': detail.id,
                    'field_name': detail.field_name,
                    'field_value': detail.field_value,
                    'timestamp': detail.timestamp.strftime('%Y-%m-%d %H:%M')
                }
            })
    return jsonify({'status': 'error'})


@app.route('/delete_detail/<int:detail_id>')
@login_required
def delete_detail(detail_id):
    detail = TicketDetail.query.get(detail_id)
    if detail:
        db.session.delete(detail)
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'})


# ----------------- 初始化应用 -----------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)