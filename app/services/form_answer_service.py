# app/services/form_answer_service.py

from typing import Any, Dict, List, Optional, Tuple, Union
from app import db
from app.models.answer import Answer
from app.models.answers_submitted import AnswerSubmitted
from app.models.form import Form
from app.models.form_answer import FormAnswer
from sqlalchemy.exc import IntegrityError
from datetime import datetime
from sqlalchemy.orm import joinedload
import logging

from app.models.user import User

logger = logging.getLogger(__name__)

from app.models.form_question import FormQuestion

class FormAnswerService:
    @staticmethod
    def create_form_answer(
        form_question_id: int,
        answer_id: int
    ) -> Tuple[Optional[FormAnswer], Optional[str]]:
        """
        Create a new form answer with comprehensive validation.
        
        Args:
            form_question_id: ID of the form question
            answer_id: ID of the answer
            current_user: Current user object for authorization
            
        Returns:
            tuple: (Created FormAnswer object or None, Error message or None)
        """
        try:
            # Verify form question exists and is not deleted
            form_question = FormQuestion.query.filter_by(
                id=form_question_id,
                is_deleted=False
            ).first()
            
            if not form_question:
                return None, "Form question not found or has been deleted"

            # Verify related form exists and is not deleted
            if form_question.form.is_deleted:
                return None, "Cannot add answers to a deleted form"

            # Verify answer exists and is not deleted
            answer = Answer.query.filter_by(
                id=answer_id,
                is_deleted=False
            ).first()
            
            if not answer:
                return None, "Answer not found or has been deleted"

            # Start transaction
            db.session.begin_nested()

            # Check for existing non-deleted mapping
            existing = FormAnswer.query.filter_by(
                form_question_id=form_question_id,
                answer_id=answer_id,
                is_deleted=False
            ).first()

            if existing:
                return None, "This answer is already mapped to this question"

            # Create new form answer
            form_answer = FormAnswer(
                form_question_id=form_question_id,
                answer_id=answer_id
            )
            db.session.add(form_answer)
            db.session.commit()

            logger.info(
                f"Created form answer mapping: Question {form_question_id} -> Answer {answer_id}"
            )
            return form_answer, None

        except IntegrityError as e:
            db.session.rollback()
            error_msg = "Database integrity error: possibly invalid IDs"
            logger.error(f"{error_msg}: {str(e)}")
            return None, error_msg
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error creating form answer: {str(e)}"
            logger.error(error_msg)
            return None, error_msg

    @staticmethod
    def bulk_create_form_answers(
        form_answers_data: List[Dict[str, Any]]
    ) -> Tuple[Optional[List[FormAnswer]], Optional[str]]:
        """
        Bulk create form answers with transaction safety.
        
        Args:
            form_answers_data: List of dictionaries containing form_question_id and answer_id
            current_user: Current user object for authorization
            
        Returns:
            tuple: (List of created FormAnswer objects or None, Error message or None)
        """
        try:
            created_answers = []
            
            # Start transaction
            db.session.begin_nested()

            # Validate all form questions and answers first
            for data in form_answers_data:
                form_question = FormQuestion.query.filter_by(
                    id=data.get('form_question_id'),
                    is_deleted=False
                ).first()
                
                if not form_question:
                    db.session.rollback()
                    return None, f"Form question {data.get('form_question_id')} not found or deleted"

                answer = Answer.query.filter_by(
                    id=data.get('answer_id'),
                    is_deleted=False
                ).first()
                
                if not answer:
                    db.session.rollback()
                    return None, f"Answer {data.get('answer_id')} not found or deleted"

                # Check for existing non-deleted mapping
                existing = FormAnswer.query.filter_by(
                    form_question_id=data['form_question_id'],
                    answer_id=data['answer_id'],
                    is_deleted=False
                ).first()
                
                if existing:
                    db.session.rollback()
                    return None, f"Answer {data['answer_id']} is already mapped to question {data['form_question_id']}"

            # Create all form answers
            for data in form_answers_data:
                form_answer = FormAnswer(
                    form_question_id=data['form_question_id'],
                    answer_id=data['answer_id']
                )
                db.session.add(form_answer)
                created_answers.append(form_answer)

            db.session.commit()
            
            logger.info(f"Successfully created {len(created_answers)} form answers")
            return created_answers, None

        except Exception as e:
            db.session.rollback()
            error_msg = f"Error in bulk creation: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
        
    @staticmethod
    def get_all_form_answers(include_deleted=False):
        """Get all form answers"""
        query = FormAnswer.query
        
        if not include_deleted:
            query = query.filter(FormAnswer.is_deleted == False)
            
        return query.order_by(FormAnswer.id).all()

    @staticmethod
    def get_form_answer(form_answer_id: int) -> Optional[FormAnswer]:
        """Get non-deleted form answer by ID with relationships"""
        return (FormAnswer.query
            .filter_by(
                id=form_answer_id,
                is_deleted=False
            )
            .options(
                joinedload(FormAnswer.form_question)
                    .joinedload(FormQuestion.form)
                    .joinedload(Form.creator),
                joinedload(FormAnswer.answer)
            )
            .first())

    @staticmethod
    def get_answers_by_question(
        form_question_id: int,
        current_user: User
    ) -> Tuple[List[FormAnswer], Optional[str]]:
        """
        Get all answers for a form question with proper authorization.
        
        Args:
            form_question_id: ID of the form question
            current_user: Current user object for authorization
            
        Returns:
            tuple: (List of FormAnswer objects, Error message or None)
        """
        try:
            # Verify form question exists and is not deleted
            form_question = FormQuestion.query.filter_by(
                id=form_question_id,
                is_deleted=False
            ).first()
            
            if not form_question:
                return [], "Form question not found or has been deleted"

            # Authorization check
            if not current_user.role.is_super_user:
                if not form_question.form.is_public and \
                   form_question.form.creator.environment_id != current_user.environment_id:
                    return [], "Unauthorized: Form question belongs to different environment"

            # Get all non-deleted form answers
            form_answers = FormAnswer.query.filter_by(
                form_question_id=form_question_id,
                is_deleted=False
            ).join(
                Answer,
                Answer.id == FormAnswer.answer_id
            ).filter(
                Answer.is_deleted == False
            ).all()

            return form_answers, None

        except Exception as e:
            error_msg = f"Error retrieving answers: {str(e)}"
            logger.error(error_msg)
            return [], error_msg

    @staticmethod
    def update_form_answer(
        form_answer_id: int,
        current_user: User,
        **kwargs
    ) -> Tuple[Optional[FormAnswer], Optional[str]]:
        """
        Update a form answer with validation and authorization.
        
        Args:
            form_answer_id: ID of the form answer to update
            current_user: Current user object for authorization
            **kwargs: Fields to update (answer_id)
            
        Returns:
            tuple: (Updated FormAnswer object or None, Error message or None)
        """
        try:
            # Verify form answer exists and is not deleted
            form_answer = FormAnswer.query.filter_by(
                id=form_answer_id,
                is_deleted=False
            ).first()
            
            if not form_answer:
                return None, "Form answer not found or has been deleted"

            # Authorization check
            if not current_user.role.is_super_user:
                if form_answer.form_question.form.creator.environment_id != current_user.environment_id:
                    return None, "Unauthorized: Form answer belongs to different environment"

            # Check if answer is already submitted
            if AnswerSubmitted.query.filter_by(
                form_answers_id=form_answer_id,
                is_deleted=False
            ).first():
                return None, "Cannot update answer that has been submitted"

            # Validate new answer if provided
            new_answer_id = kwargs.get('answer_id')
            if new_answer_id:
                new_answer = Answer.query.filter_by(
                    id=new_answer_id,
                    is_deleted=False
                ).first()
                
                if not new_answer:
                    return None, f"New answer {new_answer_id} not found or deleted"

                # Check for duplicate mapping
                existing = FormAnswer.query.filter_by(
                    form_question_id=form_answer.form_question_id,
                    answer_id=new_answer_id,
                    is_deleted=False
                ).filter(FormAnswer.id != form_answer_id).first()
                
                if existing:
                    return None, "This answer is already mapped to the question"

            # Start transaction
            db.session.begin_nested()

            # Update form answer
            for key, value in kwargs.items():
                if hasattr(form_answer, key):
                    setattr(form_answer, key, value)

            form_answer.updated_at = datetime.utcnow()
            db.session.commit()

            logger.info(f"Updated form answer {form_answer_id}")
            return form_answer, None

        except Exception as e:
            db.session.rollback()
            error_msg = f"Error updating form answer: {str(e)}"
            logger.error(error_msg)
            return None, error_msg

    @staticmethod
    def delete_form_answer(form_answer_id: int) -> tuple[bool, Union[dict, str]]:
        """
        Permanently delete a form answer and associated data
        
        Args:
            form_answer_id (int): ID of the form answer to delete
            
        Returns:
            tuple: (success: bool, result: Union[dict, str])
                    result contains either deletion statistics or error message
        """
        try:
            form_answer = FormAnswer.query.get(form_answer_id)
            
            if not form_answer:
                return False, "Form answer not found"

            # Check if answer is submitted
            submitted = AnswerSubmitted.query.filter_by(
                form_answers_id=form_answer_id,
                is_deleted=False
            ).first()
            
            if submitted:
                return False, "Cannot delete answer that has been submitted"

            # Start transaction
            db.session.begin_nested()

            # Simple deletion stats since we're performing a permanent delete
            deletion_stats = {
                'form_answer_id': form_answer_id,
                'answer_value': form_answer.answer.value if form_answer.answer else None,
                'form_question': form_answer.form_question.question.text if form_answer.form_question and form_answer.form_question.question else None
            }

            # Perform hard delete - will cascade to related records
            db.session.delete(form_answer)
            db.session.commit()
            
            logger.info(f"Form answer {form_answer_id} permanently deleted. Stats: {deletion_stats}")
            return True, deletion_stats

        except Exception as e:
            db.session.rollback()
            error_msg = f"Error deleting form answer: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    @staticmethod
    def is_answer_submitted(form_answer_id: int) -> bool:
        """Check if answer is submitted"""
        return (AnswerSubmitted.query
            .filter_by(
                form_answers_id=form_answer_id,
                is_deleted=False
            )
            .first() is not None)