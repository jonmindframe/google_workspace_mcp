"""
Google Drive Helper Functions

Shared utilities for Google Drive operations including permission checking.
"""
import re
import asyncio
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def check_public_link_permission(permissions: List[Dict[str, Any]]) -> bool:
    """
    Check if file has 'anyone with the link' permission.
    
    Args:
        permissions: List of permission objects from Google Drive API
        
    Returns:
        bool: True if file has public link sharing enabled
    """
    return any(
        p.get('type') == 'anyone' and p.get('role') in ['reader', 'writer', 'commenter']
        for p in permissions
    )


def format_public_sharing_error(file_name: str, file_id: str) -> str:
    """
    Format error message for files without public sharing.
    
    Args:
        file_name: Name of the file
        file_id: Google Drive file ID
        
    Returns:
        str: Formatted error message
    """
    return (
        f"❌ Permission Error: '{file_name}' not shared publicly. "
        f"Set 'Anyone with the link' → 'Viewer' in Google Drive sharing. "
        f"File: https://drive.google.com/file/d/{file_id}/view"
    )


def get_drive_image_url(file_id: str) -> str:
    """
    Get the correct Drive URL format for publicly shared images.
    
    Args:
        file_id: Google Drive file ID
        
    Returns:
        str: URL for embedding Drive images
    """
    return f"https://drive.google.com/uc?export=view&id={file_id}"


# Precompiled regex patterns for Drive query detection
DRIVE_QUERY_PATTERNS = [
    re.compile(r'\b\w+\s*(=|!=|>|<)\s*[\'"].*?[\'"]', re.IGNORECASE),  # field = 'value'
    re.compile(r'\b\w+\s*(=|!=|>|<)\s*\d+', re.IGNORECASE),            # field = number
    re.compile(r'\bcontains\b', re.IGNORECASE),                         # contains operator
    re.compile(r'\bin\s+parents\b', re.IGNORECASE),                     # in parents
    re.compile(r'\bhas\s*\{', re.IGNORECASE),                          # has {properties}
    re.compile(r'\btrashed\s*=\s*(true|false)\b', re.IGNORECASE),      # trashed=true/false
    re.compile(r'\bstarred\s*=\s*(true|false)\b', re.IGNORECASE),      # starred=true/false
    re.compile(r'[\'"][^\'"]+[\'"]\s+in\s+parents', re.IGNORECASE),    # 'parentId' in parents
    re.compile(r'\bfullText\s+contains\b', re.IGNORECASE),             # fullText contains
    re.compile(r'\bname\s*(=|contains)\b', re.IGNORECASE),             # name = or name contains
    re.compile(r'\bmimeType\s*(=|!=)\b', re.IGNORECASE),               # mimeType operators
]


def build_drive_list_params(
    query: str,
    page_size: int,
    drive_id: Optional[str] = None,
    include_items_from_all_drives: bool = True,
    corpora: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Helper function to build common list parameters for Drive API calls.

    Args:
        query: The search query string
        page_size: Maximum number of items to return
        drive_id: Optional shared drive ID
        include_items_from_all_drives: Whether to include items from all drives
        corpora: Optional corpus specification

    Returns:
        Dictionary of parameters for Drive API list calls
    """
    list_params = {
        "q": query,
        "pageSize": page_size,
        "fields": "nextPageToken, files(id, name, mimeType, webViewLink, iconLink, modifiedTime, size)",
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": include_items_from_all_drives,
    }

    if drive_id:
        list_params["driveId"] = drive_id
        if corpora:
            list_params["corpora"] = corpora
        else:
            list_params["corpora"] = "drive"
    elif corpora:
        list_params["corpora"] = corpora

    return list_params


async def find_or_create_folder(
    drive_service: Any,
    folder_name: str,
    drive_id: str = None,
    include_items_from_all_drives: bool = True
) -> str:
    """
    Finds a folder by name or creates it if it doesn't exist.
    Supports both My Drive and Shared Drives.
    
    Args:
        drive_service: Google Drive service instance
        folder_name: Name of the folder to find/create
        drive_id: ID of the shared drive (optional)
        include_items_from_all_drives: Whether to include items from all drives when searching
        
    Returns:
        str: Folder ID if found/created, None if failed
    """
    logger.info(f"[find_or_create_folder] Looking for folder '{folder_name}', drive_id={drive_id}")
    
    try:
        # Search for existing folder
        escaped_name = folder_name.replace("'", "\\'")
        query = f"name = '{escaped_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        
        # Build search parameters
        search_params = {
            "q": query,
            "pageSize": 10,
            "fields": "files(id, name, parents)",
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": include_items_from_all_drives
        }
        
        # Add drive-specific parameters if drive_id is provided
        if drive_id:
            search_params["corpora"] = "drive"
            search_params["driveId"] = drive_id
        
        results = await asyncio.to_thread(
            drive_service.files().list(**search_params).execute
        )
        
        folders = results.get('files', [])
        
        if folders:
            # Folder exists, return the first match
            folder_id = folders[0]['id']
            logger.info(f"[find_or_create_folder] Found existing folder '{folder_name}' with ID: {folder_id}")
            return folder_id
        
        # Folder doesn't exist, create it
        logger.info(f"[find_or_create_folder] Folder '{folder_name}' not found, creating new folder")
        
        # Determine parent folder for the new folder
        parent_folder = 'root'
        if drive_id:
            # For shared drives, the parent is the drive root
            parent_folder = drive_id
        
        # Create folder metadata
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_folder]
        }
        
        # Create the folder
        created_folder = await asyncio.to_thread(
            drive_service.files().create(
                body=folder_metadata,
                fields='id, name',
                supportsAllDrives=True
            ).execute
        )
        
        new_folder_id = created_folder.get('id')
        logger.info(f"[find_or_create_folder] Successfully created folder '{folder_name}' with ID: {new_folder_id}")
        return new_folder_id
        
    except Exception as e:
        logger.error(f"[find_or_create_folder] Error finding/creating folder '{folder_name}': {e}")
        return None