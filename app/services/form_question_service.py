# app/services/form_question_service.py

from typing import Dict, List, Optional, Tuple, Union
from app import db
from app.models.answers_submitted import AnswerSubmitted
from app.models.form import Form
from app.models.form_answer import FormAnswer
from app.models.form_question import FormQuestion
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError

from app.models.question import Question
from app.models.user import User
import logging

logger = logging.getLogger(__name__)

class FormQuestionService:
    @staticmethod
    def create_form_question(form_id, question_id, order_number=None):
        """
        Create a new form question mapping
        
        Args:
            form_id (int): ID of the form
            question_id (int): ID of the question
            order_number (int, optional): Order number for the question
            
        Returns:
            tuple: (FormQuestion, str) - Created form question or error message
        """
        try:
            # Validate form exists
            form = Form.query.get(form_id)
            if not form:
                return None, "Form not found"

            # Validate question exists
            question = Question.query.get(question_id)
            if not question:
                return None, "Question not found"

            # If no order number provided, get the next available one
            if order_number is None:
                max_order = db.session.query(db.func.max(FormQuestion.order_number))\
                    .filter_by(form_id=form_id).scalar()
                order_number = (max_order or 0) + 1

            form_question = FormQuestion(
                form_id=form_id,
                question_id=question_id,
                order_number=order_number
            )
            
            db.session.add(form_question)
            db.session.commit()
            
            # Refresh to load relationships
            db.session.refresh(form_question)
            
            return form_question, None

        except IntegrityError:
            db.session.rollback()
            return None, "Invalid form_id or question_id"
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating form question: {str(e)}")
            return None, str(e)
        
    @staticmethod
    def get_all_form_questions(
        environment_id: Optional[int] = None,
        include_relations: bool = True
    ) -> list[FormQuestion]:
        """Get all form questions with optional filtering"""
        query = FormQuestion.query.filter_by(is_deleted=False)

        if include_relations:
            query = query.options(
                joinedload(FormQuestion.form),
                joinedload(FormQuestion.question)
                    .joinedload(Question.question_type)
            )

        if environment_id:
            query = query.join(
                Form,
                User
            ).filter(
                User.environment_id == environment_id,
                User.is_deleted == False
            )

        return query.order_by(
            FormQuestion.form_id,
            FormQuestion.order_number.nullslast()
        ).all()
        
    @staticmethod
    def get_form_question_with_relations(form_question_id: int) -> Optional[FormQuestion]:
        """
        Get a specific form question with all its relationships loaded
        
        Args:
            form_question_id (int): ID of the form question to retrieve
            
        Returns:
            Optional[FormQuestion]: FormQuestion object with relationships or None if not found
            
        Raises:
            SQLAlchemyError: If there's a database error
        """
        try:
            return FormQuestion.query.options(
                joinedload(FormQuestion.form),
                joinedload(FormQuestion.question).joinedload(Question.question_type),
                joinedload(FormQuestion.form_answers).joinedload(FormAnswer.answer)
            ).get(form_question_id)
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting form question {form_question_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting form question {form_question_id}: {str(e)}")
            raise

    @staticmethod
    def get_form_question(form_question_id: int) -> Optional[FormQuestion]:
        """Get non-deleted form question by ID"""
        return (FormQuestion.query
            .filter_by(
                id=form_question_id,
                is_deleted=False
            )
            .options(
                joinedload(FormQuestion.form),
                joinedload(FormQuestion.question)
            )
            .first())

    @staticmethod
    def get_questions_by_form(form_id: int) -> Tuple[Optional[Dict], List[FormQuestion]]:
        """
        Get all non-deleted questions for a specific form
        
        Args:
            form_id: ID of the form
            
        Returns:
            Tuple containing form info and list of form questions
        """
        try:
            # Get form details first
            form = (FormQuestion.query
                .filter_by(form_id=form_id, is_deleted=False)
                .options(joinedload(FormQuestion.form))
                .first())
            
            if not form:
                return None, []
                
            # Get form questions
            questions = (FormQuestion.query
                .filter_by(
                    form_id=form_id,
                    is_deleted=False
                )
                .options(
                    joinedload(FormQuestion.question)
                        .joinedload(Question.question_type)
                )
                .order_by(FormQuestion.order_number)
                .all())
                
            return form.form, questions
                
        except Exception as e:
            logger.error(f"Error fetching form questions: {str(e)}")
            raise
        
    @staticmethod
    def reorder_questions(
        form_id: int,
        question_order: list[tuple]
    ) -> tuple[bool, Optional[str]]:
        """Update question order numbers with proper validation"""
        try:
            # Verify form exists and is active
            form = Form.query.filter_by(
                id=form_id,
                is_deleted=False
            ).first()
            
            if not form:
                return False, "Form not found or inactive"

            # Verify all questions exist and belong to the form
            order_numbers = set()
            for form_question_id, new_order in question_order:
                # Validate order number
                if new_order in order_numbers:
                    return False, f"Duplicate order number: {new_order}"
                order_numbers.add(new_order)
                
                # Check question exists and is active
                form_question = FormQuestion.query.filter_by(
                    id=form_question_id,
                    form_id=form_id,
                    is_deleted=False
                ).first()
                
                if not form_question:
                    return False, f"Form question {form_question_id} not found or not part of this form"

            # Update order numbers in a single transaction
            db.session.begin_nested()
            
            for form_question_id, new_order in question_order:
                FormQuestion.query.filter_by(id=form_question_id).update({
                    'order_number': new_order,
                    'updated_at': datetime.utcnow()
                })

            db.session.commit()
            return True, None

        except Exception as e:
            db.session.rollback()
            error_msg = f"Error reordering questions: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    @staticmethod
    def update_form_question(form_question_id, **kwargs):
        """Update a form question mapping"""
        try:
            form_question = FormQuestion.query.get(form_question_id)
            if not form_question:
                return None, "Form question not found"

            # Update fields
            for key, value in kwargs.items():
                if hasattr(form_question, key):
                    setattr(form_question, key, value)

            form_question.updated_at = datetime.utcnow()
            db.session.commit()
            return form_question, None

        except IntegrityError:
            db.session.rollback()
            return None, "Invalid question_id"
        except Exception as e:
            db.session.rollback()
            return None, str(e)

    @staticmethod
    def delete_form_question(form_question_id: int) -> tuple[bool, Union[dict, str]]:
        """
        Permanently delete a form question and associated data through cascade delete
        
        Args:
            form_question_id (int): ID of the form question to delete
            
        Returns:
            tuple: (success: bool, result: Union[dict, str])
                result contains either deletion statistics or error message
        """
        try:
            form_question = FormQuestion.query.get(form_question_id)
            
            if not form_question:
                return False, "Form question not found"

            # Start transaction
            db.session.begin_nested()

            deletion_stats = {
                'form_answers': len(form_question.form_answers),
                'answers_submitted': sum(len(fa.answers_submitted) for fa in form_question.form_answers)
            }

            # Perform hard delete - will cascade to related records due to relationship settings
            db.session.delete(form_question)
            db.session.commit()
            
            logger.info(f"Form question {form_question_id} and associated data permanently deleted. Stats: {deletion_stats}")
            return True, deletion_stats

        except Exception as e:
            db.session.rollback()
            error_msg = f"Error deleting form question: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    @staticmethod
    def bulk_create_form_questions(form_id, questions):
        """
        Bulk create form questions with proper validation
        """
        try:
            # Verify form exists and is active
            form = Form.query.filter_by(
                id=form_id,
                is_deleted=False
            ).first()
            
            if not form:
                return None, "Form not found or inactive"

            # Get current max order with soft-delete consideration
            current_max_order = db.session.query(
                db.func.max(FormQuestion.order_number)
            ).filter_by(
                form_id=form_id,
                is_deleted=False
            ).scalar() or 0

            form_questions = []
            seen_questions = set()  # To prevent duplicates
            
            for i, question_data in enumerate(questions, 1):
                question_id = question_data.get('question_id')
                
                # Prevent duplicate questions in the same form
                if question_id in seen_questions:
                    return None, f"Duplicate question ID {question_id} in request"
                seen_questions.add(question_id)
                
                # Verify question exists and is active
                question = Question.query.filter_by(
                    id=question_id,
                    is_deleted=False
                ).first()
                
                if not question:
                    return None, f"Question with ID {question_id} not found or inactive"

                # Check if question already exists in form and is not deleted
                existing = FormQuestion.query.filter_by(
                    form_id=form_id,
                    question_id=question_id,
                    is_deleted=False
                ).first()
                
                if existing:
                    return None, f"Question {question_id} is already in this form"

                # Create form question with proper order
                form_question = FormQuestion(
                    form_id=form_id,
                    question_id=question_id,
                    order_number=question_data.get('order_number', current_max_order + i)
                )
                
                db.session.add(form_question)
                form_questions.append(form_question)

            try:
                db.session.commit()
                return form_questions, None
                
            except IntegrityError as e:
                db.session.rollback()
                logger.error(f"Integrity error in bulk_create_form_questions: {str(e)}")
                return None, "Database integrity error"
                
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error in bulk_create_form_questions: {str(e)}")
            return None, str(e)