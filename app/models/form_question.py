from app import db
from app.models.question import Question
from app.models.soft_delete_mixin import SoftDeleteMixin
from app.models.timestamp_mixin import TimestampMixin

class FormQuestion(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = 'form_questions'
    
    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(db.Integer, db.ForeignKey('forms.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    order_number = db.Column(db.Integer)

    # Relationships
    form = db.relationship('Form', back_populates='form_questions')
    question = db.relationship('Question', back_populates='form_questions')
    form_answers = db.relationship('FormAnswer', back_populates='form_question', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<FormQuestion {self.form_id}:{self.question_id}>'

    def to_dict(self):
        form_dict = {
            "id": self.form.id,
            "title": self.form.title,
            "description": self.form.description,
            "creator": self.form._get_creator_dict() if hasattr(self.form, '_get_creator_dict') else None
        } if self.form else None

        return {
            'id': self.id,
            'form': form_dict,
            'question_id': self.question_id,
            'order_number': self.order_number,
            'question': self.question.to_dict() if self.question else None
        }