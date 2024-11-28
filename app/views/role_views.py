from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.controllers.role_controller import RoleController
from app.models.user import User
from app.services.auth_service import AuthService
from app.utils.permission_manager import PermissionManager, EntityType, RoleType
import logging

logger = logging.getLogger(__name__)

role_bp = Blueprint('roles', __name__)

@role_bp.route('', methods=['POST'])
@jwt_required()
@PermissionManager.require_role(RoleType.ADMIN)  # Only Admin can create roles
def create_role():
    """Create a new role - Admin only"""
    try:
        data = request.get_json()
        name = data.get('name')
        description = data.get('description')
        is_super_user = data.get('is_super_user', False)

        if not name:
            return jsonify({"error": "Name is required"}), 400
            
        # Super user roles can only be created by admins
        current_user = get_jwt_identity()
        current_user_obj = AuthService.get_current_user(current_user)
        
        if is_super_user and not current_user_obj.role.is_super_user:
            return jsonify({"error": "Only administrators can create super user roles"}), 403

        new_role, error = RoleController.create_role(name, description, is_super_user)
        if error:
            return jsonify({"error": error}), 400

        logger.info(f"Role '{name}' created successfully by {current_user}")
        return jsonify({
            "message": "Role created successfully", 
            "role": new_role.to_dict()
        }), 201

    except Exception as e:
        logger.error(f"Error creating role: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@role_bp.route('', methods=['GET'])
@jwt_required()
@PermissionManager.require_permission(action="view", entity_type=EntityType.ROLES)
def get_all_roles():
    """Get all roles with filtering based on user's role"""
    try:
        current_user = get_jwt_identity()
        current_user_obj = AuthService.get_current_user(current_user)

        roles = RoleController.get_all_roles()

        # Filter roles based on user's permissions
        if not current_user_obj.role.is_super_user:
            # Non-admin users can't see super user roles
            roles = [role for role in roles if not role.is_super_user]

        return jsonify([role.to_dict() for role in roles]), 200

    except Exception as e:
        logger.error(f"Error getting roles: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@role_bp.route('/<int:role_id>', methods=['GET'])
@jwt_required()
@PermissionManager.require_permission(action="view", entity_type=EntityType.ROLES)
def get_role(role_id):
    """Get a specific role"""
    try:
        current_user = get_jwt_identity()
        current_user_obj = AuthService.get_current_user(current_user)

        role = RoleController.get_role(role_id)
        if not role:
            return jsonify({"error": "Role not found"}), 404

        # Check access to super user roles
        if role.is_super_user and not current_user_obj.role.is_super_user:
            return jsonify({"error": "Unauthorized access"}), 403

        return jsonify(role.to_dict()), 200

    except Exception as e:
        logger.error(f"Error getting role {role_id}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@role_bp.route('/<int:role_id>', methods=['PUT'])
@jwt_required()
@PermissionManager.require_role(RoleType.ADMIN)  # Only Admin can update roles
def update_role(role_id):
    """Update a role - Admin only"""
    try:
        data = request.get_json()
        role = RoleController.get_role(role_id)
        
        if not role:
            return jsonify({"error": "Role not found"}), 404

        # Prevent modification of the main admin role
        if role.is_super_user and role_id == 1:  # Assuming 1 is the main admin role ID
            return jsonify({"error": "Cannot modify the main administrator role"}), 403

        update_fields = {
            k: v for k, v in data.items() 
            if k in ['name', 'description', 'is_super_user']
        }
        
        updated_role, error = RoleController.update_role(role_id, **update_fields)
        if error:
            return jsonify({"error": error}), 400

        logger.info(f"Role {role_id} updated successfully")
        return jsonify({
            "message": "Role updated successfully", 
            "role": updated_role.to_dict()
        }), 200

    except Exception as e:
        logger.error(f"Error updating role {role_id}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@role_bp.route('/<int:role_id>', methods=['DELETE'])
@jwt_required()
@PermissionManager.require_role(RoleType.ADMIN)  # Only Admin can delete roles
def delete_role(role_id):
    """Delete a role with cascade soft delete - Admin only"""
    try:
        # Get role with is_deleted=False check
        role = RoleController.get_role(role_id)
        if not role:
            return jsonify({"error": "Role not found"}), 404

        # Prevent deletion of the main admin role
        if role.is_super_user and role_id == 1:
            return jsonify({"error": "Cannot delete the main administrator role"}), 403

        # Get active users with this role
        active_users = User.query.filter_by(
            role_id=role_id,
            is_deleted=False
        ).all()
        
        if active_users:
            # Create a detailed response about the active users
            active_users_info = [{
                'id': user.id,
                'username': user.username,
                'full_name': f"{user.first_name} {user.last_name}",
                'email': user.email,
                'environment': {
                    'id': user.environment_id,
                    'name': user.environment.name if user.environment and not user.environment.is_deleted else None
                }
            } for user in active_users]

            return jsonify({
                "error": "Cannot delete role with active users",
                "role": {
                    "id": role.id,
                    "name": role.name,
                    "description": role.description
                },
                "active_users": {
                    "count": len(active_users),
                    "users": active_users_info
                },
                "suggestion": "Please reassign or deactivate these users before deleting this role"
            }), 400

        success, error = RoleController.delete_role(role_id)
        if success:
            logger.info(f"Role {role_id} and associated data deleted successfully")
            return jsonify({
                "message": "Role and associated permissions deleted successfully"
            }), 200
            
        return jsonify({"error": error}), 400

    except Exception as e:
        logger.error(f"Error deleting role {role_id}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@role_bp.route('/<int:role_id>/permissions/<int:permission_id>', methods=['DELETE'])
@jwt_required()
@PermissionManager.require_role(RoleType.ADMIN)  # Only Admin can manage permissions
def remove_permission_from_role(role_id, permission_id):
    """Remove permission from role - Admin only"""
    try:
        role = RoleController.get_role(role_id)
        if not role:
            return jsonify({"error": "Role not found"}), 404

        # Prevent modification of the main admin role
        if role.is_super_user and role_id == 1:
            return jsonify({"error": "Cannot modify the main administrator role"}), 403

        success = RoleController.remove_permission_from_role(role_id, permission_id)
        if success:
            logger.info(f"Permission {permission_id} removed from role {role_id}")
            return jsonify({
                "message": "Permission removed from role successfully"
            }), 200
            
        return jsonify({"error": "Failed to remove permission from role"}), 400

    except Exception as e:
        logger.error(f"Error removing permission from role: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500