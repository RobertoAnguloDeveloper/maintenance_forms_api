from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from app.services.role_permission_service import RolePermissionService
from app import db
import logging

logger = logging.getLogger(__name__)

class RolePermissionController:
    @staticmethod
    def get_all_role_permissions():
        return RolePermissionService.get_all_role_permissions()
    
    @staticmethod
    def get_roles_by_permission(permission_id: int) -> Tuple[Optional[Dict], Optional[List[Dict]]]:
        """
        Get all roles associated with a specific permission.
        
        Args:
            permission_id: ID of the permission to query
            
        Returns:
            Tuple containing permission info dict and list of associated roles dicts
        """
        permission, roles = RolePermissionService.get_roles_by_permission(permission_id)
        
        # Convert permission and roles to dicts if they exist
        permission_dict = permission.to_dict() if permission else None
        roles_dict = [role.to_dict() for role in roles] if roles else []
        
        return permission_dict, roles_dict

    @staticmethod
    def assign_permission_to_role(role_id, permission_id):
        return RolePermissionService.assign_permission_to_role(role_id, permission_id)
    
    @staticmethod
    def bulk_assign_permissions(role_id: int, permission_ids: List[int], current_user: User) -> tuple:
        """
        Bulk assign permissions to a role.
        
        Args:
            role_id (int): ID of the role
            permission_ids (list): List of permission IDs to assign
            current_user (User): Current user object for authorization
            
        Returns:
            tuple: (Created RolePermission objects or None, Error message)
        """
        return RolePermissionService.bulk_assign_permissions(
            role_id=role_id,
            permission_ids=permission_ids,
            current_user=current_user
        )
    
    @staticmethod
    def update_role_permission(role_permission_id: int, current_user_role: str, **kwargs) -> Tuple[Optional[RolePermission], Optional[str]]:
        """
        Update role permission with provided fields.
        
        Args:
            role_permission_id: ID of the role permission to update
            current_user_role: Role of the current user
            **kwargs: Fields to update
            
        Returns:
            Tuple[Optional[RolePermission], Optional[str]]: Updated role permission and error message if any
        """
        return RolePermissionService.update_role_permission(role_permission_id, current_user_role, **kwargs)

    @staticmethod
    def remove_permission_from_role(role_permission_id: int, username: str) -> tuple[bool, Union[Dict, str]]:
        """
        Remove a permission from a role.
        
        Args:
            role_permission_id (int): ID of the role-permission mapping
            username (str): Username of the user performing the action
            
        Returns:
            tuple: (Success boolean, Dict with deletion stats or error message)
        """
        return RolePermissionService.remove_permission_from_role(
            role_permission_id,
            username
        )

    @staticmethod
    def get_permissions_by_role(role_id):
        role, permissions = RolePermissionService.get_permissions_by_role(role_id)
        if not role:
            return None, None
        
        role_info = {
            'id': role.id,
            'name': role.name,
            'description': role.description
        }
        return role_info, [permission.to_dict() for permission in permissions]
    
    @staticmethod
    def get_permissions_by_user(user_id):
        return RolePermissionService.get_permissions_by_user(user_id)

    @staticmethod
    def get_permissions_by_role(role_id):
        role, permission_data = RolePermissionService.get_permissions_by_role(role_id)
        if not role:
            return None, None
        
        role_info = {
            'id': role.id,
            'name': role.name,
            'description': role.description
        }
        
        permissions_with_mapping = [
            {
                **permission.to_dict(),
                'role_permission_id': rp_id
            } 
            for rp_id, permission in permission_data
        ]
        
        return role_info, permissions_with_mapping

    @staticmethod
    def get_role_permission(role_permission_id):
        return RolePermissionService.get_role_permission(role_permission_id)