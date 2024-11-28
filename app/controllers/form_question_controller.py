# app/controllers/form_question_controller.py

from app.models.form import Form
from app.models.form_question import FormQuestion
from app.services.form_question_service import FormQuestionService
from sqlalchemy.exc import SQLAlchemyError
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class FormQuestionController:
    @staticmethod
    def create_form_question(form_id, question_id, order_number=None):
        """Create a new form question mapping"""
        return FormQuestionService.create_form_question(
            form_id=form_id,
            question_id=question_id,
            order_number=order_number
        )
        
    @staticmethod
    def get_all_form_questions(environment_id=None, include_relations=True):
        """
        Get all form questions with optional filtering
        
        Args:
            environment_id (int, optional): Filter by environment ID
            include_relations (bool): Whether to include related data
            
        Returns:
            list: List of FormQuestion objects or None if error occurs
        """
        try:
            return FormQuestionService.get_all_form_questions(
                environment_id=environment_id,
                include_relations=include_relations
            )
        except SQLAlchemyError as e:
            logger.error(f"Database error in controller getting form questions: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in controller getting form questions: {str(e)}")
            return None

    @staticmethod
    def get_form_question(form_question_id):
        """Get a specific form question mapping"""
        return FormQuestionService.get_form_question(form_question_id)
    
    @staticmethod
    def get_form_question_detail(form_question_id: int) -> Optional[FormQuestion]:
        """
        Get detailed information for a specific form question
        
        Args:
            form_question_id (int): ID of the form question
            
        Returns:
            Optional[FormQuestion]: FormQuestion object or None if not found/error
        """
        try:
            return FormQuestionService.get_form_question_with_relations(form_question_id)
        except SQLAlchemyError as e:
            logger.error(f"Database error in controller getting form question {form_question_id}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in controller getting form question {form_question_id}: {str(e)}")
            return None

    @staticmethod
    def get_questions_by_form(form_id: int) -> List[Dict]:
        """
        Get all questions for a specific form with form info shown once
        
        Args:
            form_id: ID of the form
            
        Returns:
            List of dictionaries containing form questions
        """
        form, questions = FormQuestionService.get_questions_by_form(form_id)
        
        if not form:
            return []
            
        result = []
        
        for i, question in enumerate(questions):
            question_dict = {
                'id': question.id,
                'question_id': question.question_id,
                'order_number': question.order_number,
                'question': question.question.to_dict() if question.question else None
            }
            
            # Add form info only to the first question
            if i == 0:
                question_dict['form'] = {
                    "id": form.id,
                    "title": form.title,
                    "description": form.description,
                    "creator": form._get_creator_dict() if hasattr(form, '_get_creator_dict') else None
                }
                
            result.append(question_dict)
            
        return result

    @staticmethod
    def update_form_question(form_question_id, **kwargs):
        """Update a form question mapping"""
        return FormQuestionService.update_form_question(form_question_id, **kwargs)

    @staticmethod
    def delete_form_question(form_question_id):
        """Delete a form question mapping"""
        return FormQuestionService.delete_form_question(form_question_id)

    @staticmethod
    def bulk_create_form_questions(form_id, questions):
        """
        Bulk create form questions
        
        Args:
            form_id (int): Form ID
            questions (list): List of question data
                
        Returns:
            tuple: (List of created FormQuestion objects, error message)
        """
        try:
            # Validate form exists
            form = Form.query.get(form_id)
            if not form:
                return None, "Form not found"

            # Create form questions
            form_questions, error = FormQuestionService.bulk_create_form_questions(form_id, questions)
            
            if error:
                return None, error
                
            return form_questions, None

        except Exception as e:
            logger.error(f"Error in bulk_create_form_questions controller: {str(e)}")
            return None, str(e)