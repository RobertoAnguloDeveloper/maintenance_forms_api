from asyncio.log import logger
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.controllers import form_controller
from app.controllers.form_controller import FormController
from app.controllers.user_controller import UserController
from app.models.form import Form
from app.models.form_answer import FormAnswer
from app.models.form_question import FormQuestion
from app.models.form_submission import FormSubmission
from app.models.question import Question
from app.models.role import Role
from app.services.auth_service import AuthService
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from app import db
from app.utils.permission_manager import PermissionManager, EntityType, ActionType, RoleType
import logging

logger = logging.getLogger(__name__)
form_bp = Blueprint('forms', __name__)

@form_bp.route('', methods=['GET'])
@jwt_required()
@PermissionManager.require_permission(action="view", entity_type=EntityType.FORMS)
def get_all_forms():
    """Get all forms with role-based filtering"""
    try:
        current_user = get_jwt_identity()
        user = AuthService.get_current_user(current_user)
        
        is_public = request.args.get('is_public', type=bool)
        
        # Role-based access control
        if user.role.name == RoleType.TECHNICIAN:
            # Technicians can only see public forms
            forms = FormController.get_public_forms()
        elif user.role.name in [RoleType.SUPERVISOR, RoleType.SITE_MANAGER]:
            # Supervisors and Site Managers see forms in their environment
            forms = FormController.get_forms_by_environment(user.environment_id)
        else:
            # Admins see all forms
            forms = FormController.get_all_forms(is_public=is_public)
        
        return jsonify([form.to_dict() for form in forms]), 200
        
    except Exception as e:
        logger.error(f"Error getting forms: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@form_bp.route('/<int:form_id>', methods=['GET'])
@jwt_required()
@PermissionManager.require_permission(action="view", entity_type=EntityType.FORMS)
def get_form(form_id):
    """Get a specific form with role-based access control"""
    try:
        current_user = get_jwt_identity()
        user = AuthService.get_current_user(current_user)
        
        form = FormController.get_form(form_id)
        if not form:
            return jsonify({"error": "Form not found"}), 404

        # Role-based access control using RoleType
        if user.role.name == RoleType.TECHNICIAN:
            if not form.is_public:
                return jsonify({"error": "Unauthorized access"}), 403
        elif user.role.name in [RoleType.SUPERVISOR, RoleType.SITE_MANAGER]:
            if form.creator.environment_id != user.environment_id:
                return jsonify({"error": "Unauthorized access"}), 403

        return jsonify(form.to_dict()), 200
        
    except Exception as e:
        logger.error(f"Error getting form {form_id}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    
@form_bp.route('/environment/<int:environment_id>', methods=['GET'])
@jwt_required()
@PermissionManager.require_permission(action="view", entity_type=EntityType.FORMS)
def get_forms_by_environment(environment_id):
    """Get all forms associated with an environment"""
    try:
        print(f"Accessing forms for environment ID: {environment_id}")  # Debug log
        
        current_user = get_jwt_identity()
        user = AuthService.get_current_user(current_user)
        print(f"Current user: {user.username}, Environment: {user.environment_id}")  # Debug log

        # If user is not admin, they can only see forms from their environment
        if not user.role.is_super_user and user.environment_id != environment_id:
            print(f"Unauthorized access attempt by {user.username}")  # Debug log
            return jsonify({"error": "Unauthorized access"}), 403

        result = FormController.get_forms_by_environment(environment_id)
        
        if result is None:
            print(f"Environment {environment_id} not found")  # Debug log
            return jsonify({"error": "Environment not found"}), 404

        print(f"Found {len(result)} forms for environment {environment_id}")  # Debug log
        return jsonify({"forms": result}), 200

    except Exception as e:
        logger.error(f"Error getting forms by environment: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    
@form_bp.route('/public', methods=['GET'])
@jwt_required()
def get_public_forms():
    """Get all public forms"""
    try:
        result = FormController.get_public_forms()
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting public forms: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    
@form_bp.route('/creator/<string:username>', methods=['GET'])
@jwt_required()
@PermissionManager.require_permission(action="view", entity_type=EntityType.FORMS)
def get_forms_by_creator(username: str):
    """
    Get all forms created by a specific username with proper authorization
    """
    try:
        current_user = get_jwt_identity()
        user = AuthService.get_current_user(current_user)

        # Get the forms through controller
        forms = FormController.get_forms_by_creator(username)
        
        if forms is None:
            return jsonify({
                "error": "Creator not found or has been deleted"
            }), 404

        # For non-admin users, filter based on role
        if not user.role.is_super_user:
            if user.role.name == RoleType.TECHNICIAN:
                # Technicians can only see public forms
                forms = [form for form in forms if form['is_public']]
            elif user.role.name in [RoleType.SITE_MANAGER, RoleType.SUPERVISOR]:
                # Site Managers and Supervisors can only see forms in their environment
                forms = [
                    form for form in forms 
                    if form['created_by']['environment']['id'] == user.environment_id
                ]

        return jsonify(forms), 200

    except Exception as e:
        logger.error(f"Error getting forms by creator {username}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@form_bp.route('', methods=['POST'])
@jwt_required()
@PermissionManager.require_permission(action="create", entity_type=EntityType.FORMS)
def create_form():
    try:
        data = request.get_json()
        current_user = get_jwt_identity()
        logger.debug(f"Current user creating form: {current_user}")
        
        # First validate if we have data
        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Validate required fields
        required_fields = ['title']
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400

        # Get the user who will be the form creator
        if data.get('user_id'):
            # If user_id is provided, verify if current user has permission to create forms for others
            current_user_obj = AuthService.get_current_user(current_user)
            if not current_user_obj:
                logger.error(f"Current user not found: {current_user}")
                return jsonify({"error": "Authentication error"}), 401

            if not current_user_obj.role.is_super_user:
                logger.warning(f"Non-admin user {current_user} attempted to create form for another user")
                return jsonify({
                    "error": "Permission denied",
                    "message": "Only administrators can create forms for other users"
                }), 403

            # Get the target user
            user = UserController.get_user(data.get('user_id'))
            if not user:
                logger.error(f"Target user not found: {data.get('user_id')}")
                return jsonify({
                    "error": "Invalid user_id",
                    "message": "The specified user does not exist"
                }), 404
        else:
            # Use current user as form creator
            user = AuthService.get_current_user(current_user)
            if not user:
                logger.error(f"User not found: {current_user}")
                return jsonify({"error": "User not found"}), 404

        logger.debug(f"Creating form with data: {data}")

        try:
            new_form, error = FormController.create_form(
                title=data['title'],
                description=data.get('description'),
                user_id=user.id,
                is_public=data.get('is_public', False)
            )

            if error:
                logger.error(f"Error creating form: {error}")
                return jsonify({"error": error}), 400

            logger.info(f"Form created successfully by user {user.username}")
            return jsonify({
                "message": "Form created successfully",
                "form": new_form.to_dict(),
                "form_creator": user.username
            }), 201

        except Exception as e:
            logger.error(f"Database error while creating form: {str(e)}")
            return jsonify({"error": "Database error", "details": str(e)}), 500

    except Exception as e:
        logger.error(f"Error in create_form: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@form_bp.route('/<int:form_id>/questions', methods=['POST'])
@jwt_required()
@PermissionManager.require_permission(action="update", entity_type=EntityType.FORMS)
def add_questions_to_form(form_id):
    """Add new questions to an existing form"""
    try:
        current_user = get_jwt_identity()
        user = AuthService.get_current_user(current_user)
        
        # Get the form
        form = FormController.get_form(form_id)
        if not form:
            return jsonify({"error": "Form not found"}), 404
            
        # Check environment access for non-admin roles
        if not user.role.is_super_user:
            if form.creator.environment_id != user.environment_id:
                return jsonify({"error": "Unauthorized access"}), 403

        data = request.get_json()
        if 'questions' not in data:
            return jsonify({"error": "Questions are required"}), 400

        updated_form, error = FormController.add_questions_to_form(
            form_id=form_id,
            questions=data['questions']
        )

        if error:
            return jsonify({"error": error}), 400

        logger.info(f"Questions added to form {form_id} by user {user.username}")
        return jsonify({
            "message": "Questions added successfully",
            "form": updated_form.to_dict()
        }), 200

    except Exception as e:
        logger.error(f"Error adding questions to form {form_id}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@form_bp.route('/<int:form_id>/submissions', methods=['GET'])
@jwt_required()
@PermissionManager.require_permission(action="view", entity_type=EntityType.SUBMISSIONS)
def get_form_submissions(form_id):
    """Get all submissions for a specific form"""
    try:
        current_user = get_jwt_identity()
        user = AuthService.get_current_user(current_user)
        
        # Get the form
        form = FormController.get_form(form_id)
        if not form:
            return jsonify({"error": "Form not found"}), 404
            
        # For technicians, only show their own submissions
        if user.role.name == RoleType.TECHNICIAN:
            submissions = [s for s in form.submissions if s.submitted_by == current_user]
        # For other non-admin roles, check environment access
        elif not user.role.is_super_user:
            if form.creator.environment_id != user.environment_id:
                return jsonify({"error": "Unauthorized access"}), 403
            submissions = form.submissions
        # Admins can see all submissions
        else:
            submissions = form.submissions
            
        return jsonify([{
            'id': submission.id,
            'form_id': submission.form_id,
            'submitted_by': submission.submitted_by,
            'submitted_at': submission.submitted_at.isoformat() if submission.submitted_at else None,
            'answers': [{
                'question': answer.form_answer.form_question.question.text,
                'answer': answer.form_answer.answer.value,
                'remarks': answer.form_answer.remarks
            } for answer in submission.answers_submitted],
            'attachments': [{
                'id': attachment.id,
                'file_type': attachment.file_type,
                'file_path': attachment.file_path,
                'is_signature': attachment.is_signature
            } for attachment in submission.attachments]
        } for submission in submissions]), 200

    except Exception as e:
        logger.error(f"Error getting submissions for form {form_id}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@form_bp.route('/<int:form_id>/statistics', methods=['GET'])
@jwt_required()
@PermissionManager.require_permission(action="view", entity_type=EntityType.FORMS)
def get_form_statistics(form_id):
    """Get statistics for a specific form"""
    try:
        current_user = get_jwt_identity()
        user = AuthService.get_current_user(current_user)
        
        # Get the form
        form = FormController.get_form(form_id)
        if not form:
            return jsonify({"error": "Form not found"}), 404
            
        # Technicians can't access statistics
        if user.role.name == RoleType.TECHNICIAN:
            return jsonify({"error": "Unauthorized access"}), 403
            
        # For other non-admin roles, check environment access
        if not user.role.is_super_user:
            if form.creator.environment_id != user.environment_id:
                return jsonify({"error": "Unauthorized access"}), 403

        stats = FormController.get_form_statistics(form_id)
        if not stats:
            return jsonify({"error": "Error generating statistics"}), 400

        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"Error getting statistics for form {form_id}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@form_bp.route('/<int:form_id>', methods=['PUT'])
@jwt_required()
@PermissionManager.require_permission(action="update", entity_type=EntityType.FORMS)
def update_form(form_id):
    """Update a form with role-based access control"""
    try:
        current_user = get_jwt_identity()
        user = AuthService.get_current_user(current_user)
        
        # Get the form
        form = FormController.get_form(form_id)
        if not form:
            return jsonify({"error": "Form not found"}), 404
            
        # Check environment access for non-admin roles
        if not user.role.is_super_user:
            if form.creator.environment_id != user.environment_id:
                return jsonify({
                    "error": "Unauthorized",
                    "message": "You can only update forms in your environment"
                }), 403

        # Get and validate update data
        data = request.get_json()
        if not data:
            return jsonify({"error": "No update data provided"}), 400

        allowed_fields = ['title', 'description', 'is_public']
        update_data = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_data:
            return jsonify({"error": "No valid fields to update"}), 400
        
        # Additional validation for public forms
        if 'is_public' in update_data:
            if user.role.name == RoleType.SUPERVISOR and update_data['is_public']:
                return jsonify({
                    "error": "Unauthorized",
                    "message": "Supervisors cannot make forms public"
                }), 403

        # Special handling for admin-only operations
        if not user.role.is_super_user:
            # Prevent changing form ownership or environment
            restricted_fields = ['user_id', 'environment_id']
            if any(field in data for field in restricted_fields):
                return jsonify({
                    "error": "Unauthorized",
                    "message": "Only administrators can change form ownership or environment"
                }), 403

        result = FormController.update_form(form_id, **update_data)
        
        if result.get("error"):
            return jsonify({"error": result["error"]}), 400
            
        logger.info(f"Form {form_id} updated successfully by user {user.username}")
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error updating form {form_id}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    
@form_bp.route('/<int:form_id>', methods=['DELETE'])
@jwt_required()
@PermissionManager.require_permission(action="delete", entity_type=EntityType.FORMS)
def delete_form(form_id):
    """Delete a form with cascade soft delete"""
    try:
        current_user = get_jwt_identity()
        user = AuthService.get_current_user(current_user)
        
        # Get the form checking is_deleted=False
        form = FormController.get_form(form_id)
        if not form:
            return jsonify({"error": "Form not found"}), 404

        # Access control checks
        if not user.role.is_super_user:
            # Check environment access
            if form.creator.environment_id != user.environment_id:
                return jsonify({
                    "error": "Unauthorized",
                    "message": "You can only delete forms in your environment"
                }), 403

        # Check for active submissions if user is not admin or site manager
        if user.role.name not in [RoleType.ADMIN, RoleType.SITE_MANAGER]:
            active_submissions = FormSubmission.query.filter_by(
                form_id=form_id,
                is_deleted=False
            ).count()
            
            if active_submissions > 0:
                return jsonify({
                    "error": "Cannot delete form with active submissions",
                    "active_submissions": active_submissions
                }), 400

        success, result = FormController.delete_form(form_id)
        if success:
            logger.info(f"Form {form_id} and associated data deleted by {user.username}")
            return jsonify({
                "message": "Form and associated data deleted successfully",
                "deleted_items": result
            }), 200
            
        return jsonify({"error": result}), 400

    except Exception as e:
        logger.error(f"Error deleting form {form_id}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500