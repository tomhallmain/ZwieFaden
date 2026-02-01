"""LLM-based analyzer for determining the best version of a tool module."""

import hashlib
from typing import List, Dict, Optional, Set, Tuple
from extensions.llm import LLM, LLMResponseException


class DiffLLMAnalyzer:
    """Analyzer that uses LLM to determine the best version of a tool module."""
    
    def __init__(self, model_name: str = "deepseek-r1:14b"):
        """Initialize the analyzer with an LLM instance."""
        self.llm = LLM(model_name=model_name)
    
    def _detect_identical_files(self, files_content: List[str]) -> Dict[int, Set[int]]:
        """
        Detect identical files by content hash.
        
        Returns:
            Dictionary mapping file index to set of indices of identical files (including itself)
        """
        file_hashes = {}
        for i, content in enumerate(files_content):
            content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            file_hashes[i] = content_hash
        
        # Group files by hash
        hash_to_indices = {}
        for idx, content_hash in file_hashes.items():
            if content_hash not in hash_to_indices:
                hash_to_indices[content_hash] = []
            hash_to_indices[content_hash].append(idx)
        
        # Build result: each file maps to set of all identical files
        identical_groups = {}
        for indices in hash_to_indices.values():
            indices_set = set(indices)
            for idx in indices:
                identical_groups[idx] = indices_set
        
        return identical_groups
    
    def _get_unique_file_indices(self, files_content: List[str]) -> List[int]:
        """
        Get indices of unique files (one representative from each identical group).
        
        Returns:
            List of file indices representing unique files
        """
        identical_groups = self._detect_identical_files(files_content)
        seen_groups = set()
        unique_indices = []
        
        for idx in range(len(files_content)):
            group = identical_groups[idx]
            group_tuple = tuple(sorted(group))
            if group_tuple not in seen_groups:
                seen_groups.add(group_tuple)
                # Use the first file in the group as representative
                unique_indices.append(min(group))
        
        return unique_indices
    
    def analyze_versions(
        self,
        files_content: List[str],
        file_metadata: List[Dict],
        diff_matrix: List[Dict],
        target_context: Optional[str] = None,
        requirements: Optional[str] = None
    ) -> Dict:
        """
        Analyze multiple versions of a tool module to determine the best one.
        
        Args:
            files_content: List of file contents as strings
            file_metadata: List of metadata dictionaries for each file
            diff_matrix: List of diff comparison results
            target_context: Optional description of the target context/application
            requirements: Optional specific requirements for the new version
            
        Returns:
            Dictionary with analysis results including recommendation
        """
        # Build the prompt
        prompt = self._build_analysis_prompt(
            files_content, file_metadata, diff_matrix, target_context, requirements
        )
        
        try:
            result = self.llm.generate_response(prompt, timeout=300)
            analysis_text = result.response
            
            # Try to extract structured information
            recommendation = self._extract_recommendation(analysis_text, len(files_content))
            
            return {
                'analysis': analysis_text,
                'recommendation': recommendation,
                'raw_response': result.response
            }
        except LLMResponseException as e:
            return {
                'error': str(e),
                'analysis': None,
                'recommendation': None
            }
    
    def generate_merged_version(
        self,
        files_content: List[str],
        file_metadata: List[Dict],
        diff_matrix: List[Dict],
        target_context: str,
        requirements: Optional[str] = None,
        base_file_index: Optional[int] = None
    ) -> Dict:
        """
        Generate a new merged version of the tool module.
        
        Args:
            files_content: List of file contents as strings
            file_metadata: List of metadata dictionaries for each file
            diff_matrix: List of diff comparison results
            target_context: Description of the target context/application
            requirements: Optional specific requirements
            base_file_index: Optional index of the file to use as base
            
        Returns:
            Dictionary with the generated code and explanation
        """
        prompt = self._build_generation_prompt(
            files_content, file_metadata, diff_matrix, target_context, 
            requirements, base_file_index
        )
        
        try:
            result = self.llm.generate_response(prompt, timeout=600)
            generated_code = self._extract_code(result.response)
            
            return {
                'code': generated_code,
                'explanation': result.response,
                'raw_response': result.response
            }
        except LLMResponseException as e:
            return {
                'error': str(e),
                'code': None,
                'explanation': None
            }
    
    def _build_analysis_prompt(
        self,
        files_content: List[str],
        file_metadata: List[Dict],
        diff_matrix: List[Dict],
        target_context: Optional[str],
        requirements: Optional[str]
    ) -> str:
        """Build the prompt for version analysis."""
        prompt_parts = []
        
        prompt_parts.append("You are analyzing multiple versions of a tool module used in different applications.")
        prompt_parts.append("Your goal is to determine which version has the most up-to-date features")
        prompt_parts.append("and would be the best basis for using the same tool in a new context.\n")
        prompt_parts.append("IMPORTANT: Ignore context-dependent differences such as:")
        prompt_parts.append("- Application-specific configuration values (API keys, paths, etc.)")
        prompt_parts.append("- Hardcoded paths or URLs specific to an application")
        prompt_parts.append("- Application-specific imports or dependencies")
        prompt_parts.append("- Comments or documentation referring to specific applications")
        prompt_parts.append("- Property names or values that are specific to one application's use case")
        prompt_parts.append("\nFocus on:")
        prompt_parts.append("- Structural differences (new classes, methods, functions)")
        prompt_parts.append("- Algorithmic improvements or bug fixes")
        prompt_parts.append("- Feature additions or enhancements")
        prompt_parts.append("- Code quality improvements (error handling, type hints, etc.)")
        prompt_parts.append("- General-purpose functionality vs application-specific code\n")
        
        if target_context:
            prompt_parts.append(f"TARGET CONTEXT: {target_context}\n")
        
        if requirements:
            prompt_parts.append(f"SPECIFIC REQUIREMENTS: {requirements}\n")
        
        prompt_parts.append("=" * 80)
        prompt_parts.append("FILE METADATA")
        prompt_parts.append("=" * 80)
        
        for i, metadata in enumerate(file_metadata):
            # Use 1-based indexing for user-facing display
            prompt_parts.append(f"\nFile {i+1}: {metadata.get('filename', 'unknown')}")
            prompt_parts.append(f"  Path: {metadata.get('filepath', 'unknown')}")
            prompt_parts.append(f"  Directory Context: {metadata.get('directory_context', 'unknown')}")
            prompt_parts.append(f"  Modification Time: {metadata.get('modification_time', 'unknown')}")
            prompt_parts.append(f"  Size: {metadata.get('size', 0)} bytes")
            prompt_parts.append(f"  Lines: {metadata.get('line_count', 0)}")
        
        # Detect identical files to optimize prompt
        identical_groups = self._detect_identical_files(files_content)
        unique_indices = self._get_unique_file_indices(files_content)
        
        prompt_parts.append("\n" + "=" * 80)
        prompt_parts.append("FILE CONTENTS")
        prompt_parts.append("=" * 80)
        
        # Note about identical files
        identical_notes = []
        for idx in range(len(files_content)):
            group = identical_groups[idx]
            if len(group) > 1:
                # This file has duplicates
                other_indices = sorted([i for i in group if i != idx])
                if other_indices:
                    other_files = [f"File {i+1}" for i in other_indices]
                    identical_notes.append(f"File {idx+1} is identical to: {', '.join(other_files)}")
        
        if identical_notes:
            prompt_parts.append("\n**Note on Identical Files:**")
            for note in identical_notes:
                prompt_parts.append(f"- {note}")
            prompt_parts.append("Only unique file contents are shown below to reduce prompt length.\n")
        
        # Only include unique files
        for unique_idx in unique_indices:
            content = files_content[unique_idx]
            metadata = file_metadata[unique_idx]
            filename = metadata.get('filename', 'unknown')
            dir_context = metadata.get('directory_context', 'unknown')
            filepath = metadata.get('filepath', 'unknown')
            
            # Check if this file has duplicates
            group = identical_groups[unique_idx]
            if len(group) > 1:
                other_indices = sorted([i for i in group if i != unique_idx])
                other_files = [f"File {i+1}: {file_metadata[i].get('filename', 'unknown')} (from {file_metadata[i].get('directory_context', 'unknown')})" for i in other_indices]
                prompt_parts.append(f"\n**File {unique_idx+1}**: {filename} (from {dir_context})")
                prompt_parts.append(f"**Also identical to:** {', '.join(other_files)}")
            else:
                prompt_parts.append(f"\n**File {unique_idx+1}**: {filename} (from {dir_context})")
            
            prompt_parts.append(f"Full Path: {filepath}")
            prompt_parts.append(f"```python")
            prompt_parts.append(content)
            prompt_parts.append(f"```")
        
        prompt_parts.append("=" * 80)
        prompt_parts.append("DIFF COMPARISONS")
        prompt_parts.append("=" * 80)
        
        # Filter out diffs between identical files
        identical_groups = self._detect_identical_files(files_content)
        relevant_diffs = []
        skipped_diffs = []
        
        for comp in diff_matrix:
            idx_a = comp.get('file_a_index')
            idx_b = comp.get('file_b_index')
            
            # Check if these files are identical
            if idx_a is not None and idx_b is not None:
                group_a = identical_groups.get(idx_a, {idx_a})
                group_b = identical_groups.get(idx_b, {idx_b})
                if group_a == group_b:
                    # Files are identical, skip this diff
                    meta_a = comp['metadata_a']
                    meta_b = comp['metadata_b']
                    filename_a = meta_a.get('filename', 'unknown')
                    filename_b = meta_b.get('filename', 'unknown')
                    dir_a = meta_a.get('directory_context', 'unknown')
                    dir_b = meta_b.get('directory_context', 'unknown')
                    skipped_diffs.append(f"File {idx_a+1}: {filename_a} (from {dir_a}) vs File {idx_b+1}: {filename_b} (from {dir_b})")
                    continue
            
            relevant_diffs.append(comp)
        
        if skipped_diffs:
            prompt_parts.append("\n**Skipped Comparisons (identical files):**")
            for skipped in skipped_diffs:
                prompt_parts.append(f"- {skipped}")
            prompt_parts.append("")
        
        if not relevant_diffs:
            prompt_parts.append("\n**All files are identical - no differences to compare.**\n")
        else:
            for i, comp in enumerate(relevant_diffs):
                if i > 0: # Add a blank line between comparisons, but not before the first one
                    prompt_parts.append("") 
                meta_a = comp['metadata_a']
                meta_b = comp['metadata_b']
                idx_a = comp.get('file_a_index')
                idx_b = comp.get('file_b_index')
                filename_a = meta_a.get('filename', 'unknown')
                filename_b = meta_b.get('filename', 'unknown')
                dir_a = meta_a.get('directory_context', 'unknown')
                dir_b = meta_b.get('directory_context', 'unknown')
                # Use numerical indices (1-based) for consistency with rest of prompt
                if idx_a is not None and idx_b is not None:
                    prompt_parts.append(f"**File {idx_a+1}: {filename_a} (from {dir_a}) vs File {idx_b+1}: {filename_b} (from {dir_b})**")
                else:
                    prompt_parts.append(f"**{filename_a} (from {dir_a}) vs {filename_b} (from {dir_b})**")
                prompt_parts.append(f"Statistics:")
                prompt_parts.append(f"- Insertions: {comp['statistics']['insertions']}")
                prompt_parts.append(f"- Deletions: {comp['statistics']['deletions']}")
                prompt_parts.append(f"- Similarity: {comp['statistics']['similarity_ratio']:.2%}")
                prompt_parts.append(f"Unified Diff:")
                # Clean up unified diff - remove all blank lines
                cleaned_diff = self._clean_unified_diff(comp['unified_diff'])
                # Strip any remaining leading/trailing blank lines from the cleaned diff
                cleaned_diff = cleaned_diff.strip()
                if cleaned_diff:
                    prompt_parts.append(f"```diff")
                    prompt_parts.append(cleaned_diff)
                    prompt_parts.append(f"```")
        
        prompt_parts.append("=" * 80)
        prompt_parts.append("ANALYSIS REQUEST")
        prompt_parts.append("=" * 80)
        prompt_parts.append("\nPlease analyze these versions and provide:")
        prompt_parts.append("1. Which version appears to be the most up-to-date and why")
        prompt_parts.append("   (Focus on actual features, not context-specific configurations)")
        prompt_parts.append("2. What features are unique to each version")
        prompt_parts.append("   (Exclude context-dependent differences like API keys or app-specific paths)")
        prompt_parts.append("3. Which version would be the best basis for the target context and why")
        prompt_parts.append("4. Any recommendations for merging features from different versions")
        prompt_parts.append("\nWhen comparing versions, distinguish between:")
        prompt_parts.append("- Core functionality improvements (these matter)")
        prompt_parts.append("- Application-specific customizations (ignore these)")
        prompt_parts.append("\nIMPORTANT: When referencing files in your analysis, use their differentiable names.")
        prompt_parts.append("Include the directory context or project name to distinguish between files with the same name.")
        
        # Use actual file from current request as example
        if file_metadata:
            example_metadata = file_metadata[0]
            example_filename = example_metadata.get('filename', 'unknown')
            example_dir = example_metadata.get('directory_context', 'unknown')
            example_format = f"'{example_filename} (from {example_dir})'"
            prompt_parts.append(f"For example, use {example_format}")
            prompt_parts.append(f"rather than just 'File 1' or '{example_filename}'.")
        
        prompt_parts.append("\nFormat your response with clear sections and reasoning.")
        
        return '\n'.join(prompt_parts)
    
    def _build_generation_prompt(
        self,
        files_content: List[str],
        file_metadata: List[Dict],
        diff_matrix: List[Dict],
        target_context: str,
        requirements: Optional[str],
        base_file_index: Optional[int]
    ) -> str:
        """Build the prompt for code generation."""
        prompt_parts = []
        
        prompt_parts.append("You are generating a new version of a tool module based on multiple existing versions.")
        prompt_parts.append(f"TARGET CONTEXT: {target_context}\n")
        prompt_parts.append("IMPORTANT: When generating the merged version:")
        prompt_parts.append("- DO NOT include application-specific configuration values (API keys, paths, etc.)")
        prompt_parts.append("- DO NOT include hardcoded paths or URLs from specific applications")
        prompt_parts.append("- DO include all core functionality and features from all versions")
        prompt_parts.append("- DO include improvements in error handling, type hints, and code quality")
        prompt_parts.append("- DO make the code general-purpose and adaptable to the target context")
        prompt_parts.append("- DO use placeholder values or configuration patterns instead of hardcoded app-specific values\n")
        
        if requirements:
            prompt_parts.append(f"SPECIFIC REQUIREMENTS: {requirements}\n")
        
        if base_file_index is not None:
            # Convert to 1-based index for display
            base_metadata = file_metadata[base_file_index]
            base_filename = base_metadata.get('filename', 'unknown')
            base_dir = base_metadata.get('directory_context', 'unknown')
            prompt_parts.append(f"BASE FILE: Using File {base_file_index+1}: {base_filename} (from {base_dir}) as the starting point.\n")
        
        # Detect identical files to optimize prompt
        identical_groups = self._detect_identical_files(files_content)
        unique_indices = self._get_unique_file_indices(files_content)
        
        prompt_parts.append("=" * 80)
        prompt_parts.append("EXISTING VERSIONS")
        prompt_parts.append("=" * 80)
        
        # Note about identical files
        identical_notes = []
        for idx in range(len(files_content)):
            group = identical_groups[idx]
            if len(group) > 1:
                # This file has duplicates
                other_indices = sorted([i for i in group if i != idx])
                if other_indices:
                    other_files = [f"File {i+1}" for i in other_indices]
                    identical_notes.append(f"File {idx+1} is identical to: {', '.join(other_files)}")
        
        if identical_notes:
            prompt_parts.append("\n**Note on Identical Files:**")
            for note in identical_notes:
                prompt_parts.append(f"- {note}")
            prompt_parts.append("Only unique file contents are shown below to reduce prompt length.\n")
        
        # Only include unique files
        for unique_idx in unique_indices:
            content = files_content[unique_idx]
            metadata = file_metadata[unique_idx]
            filename = metadata.get('filename', 'unknown')
            dir_context = metadata.get('directory_context', 'unknown')
            filepath = metadata.get('filepath', 'unknown')
            
            # Check if this file has duplicates
            group = identical_groups[unique_idx]
            if len(group) > 1:
                other_indices = sorted([i for i in group if i != unique_idx])
                other_files = [f"File {i+1}: {file_metadata[i].get('filename', 'unknown')} (from {file_metadata[i].get('directory_context', 'unknown')})" for i in other_indices]
                prompt_parts.append(f"\n**File {unique_idx+1}**: {filename} (from {dir_context})")
                prompt_parts.append(f"**Also identical to:** {', '.join(other_files)}")
            else:
                prompt_parts.append(f"\n**File {unique_idx+1}**: {filename} (from {dir_context})")
            
            prompt_parts.append(f"Full Path: {filepath}")
            prompt_parts.append(f"```python")
            prompt_parts.append(content)
            prompt_parts.append(f"```")
        
        prompt_parts.append("=" * 80)
        prompt_parts.append("DIFF SUMMARY")
        prompt_parts.append("=" * 80)
        
        for comp in diff_matrix:
            meta_a = comp['metadata_a']
            meta_b = comp['metadata_b']
            filename_a = meta_a.get('filename', 'unknown')
            filename_b = meta_b.get('filename', 'unknown')
            dir_a = meta_a.get('directory_context', 'unknown')
            dir_b = meta_b.get('directory_context', 'unknown')
            # Show filenames with directory context
            prompt_parts.append(f"\n{filename_a} ({dir_a}) vs {filename_b} ({dir_b}):")
            prompt_parts.append(f"  Changes: {comp['statistics']['total_changes']} lines")
            prompt_parts.append(f"  Similarity: {comp['statistics']['similarity_ratio']:.2%}")
        
        prompt_parts.append("\n" + "=" * 80)
        prompt_parts.append("GENERATION REQUEST")
        prompt_parts.append("=" * 80)
        prompt_parts.append("\nGenerate a new version of this tool module that:")
        prompt_parts.append("1. Is appropriate for the target context")
        prompt_parts.append("2. Incorporates the best features from all versions")
        prompt_parts.append("3. Meets the specified requirements (if any)")
        prompt_parts.append("4. Maintains compatibility and best practices")
        prompt_parts.append("5. Excludes application-specific configurations (use placeholders or config patterns)")
        prompt_parts.append("\nProvide the complete code for the new module.")
        prompt_parts.append("Include comments explaining key decisions and feature integrations.")
        prompt_parts.append("Use generic placeholders or configuration patterns for any values that were")
        prompt_parts.append("application-specific in the original versions.")
        
        return '\n'.join(prompt_parts)
    
    def _extract_recommendation(self, analysis_text: str, num_files: int) -> Optional[Dict]:
        """Extract structured recommendation from LLM response."""
        # Try to find file index mentioned in the response
        recommendation = {
            'recommended_file_index': None,
            'confidence': None,
            'reasoning': analysis_text[:500]  # First 500 chars as reasoning
        }
        
        # Look for patterns like "File 1", "version 2", etc. (1-based) or "File 0" (0-based for backwards compatibility)
        import re
        for i in range(num_files):
            # Check for 1-based indexing (current format)
            patterns_1based = [
                rf'\bFile\s+{i+1}\b',
                rf'\bversion\s+{i+1}\b',
                rf'\bfile\s+{i+1}\b',
                rf'\bFile\s+{i+1}:'
            ]
            # Also check for 0-based (backwards compatibility)
            patterns_0based = [
                rf'\bFile\s+{i}\b',
                rf'\bversion\s+{i}\b',
                rf'\bfile\s+{i}\b',
                rf'\bFile\s+{i}:'
            ]
            for pattern in patterns_1based + patterns_0based:
                if re.search(pattern, analysis_text, re.IGNORECASE):
                    recommendation['recommended_file_index'] = i
                    break
            if recommendation['recommended_file_index'] is not None:
                break
        
        return recommendation
    
    def _extract_code(self, response: str) -> str:
        """Extract code blocks from LLM response."""
        import re
        
        # Look for code blocks
        code_block_pattern = r'```(?:\w+)?\n(.*?)```'
        matches = re.findall(code_block_pattern, response, re.DOTALL)
        
        if matches:
            # Return the largest code block (likely the main one)
            return max(matches, key=len).strip()
        
        # If no code blocks, look for indented sections that might be code
        lines = response.split('\n')
        code_lines = []
        in_code = False
        
        for line in lines:
            # Heuristic: if line starts with significant indentation or looks like code
            if (line.strip().startswith(('def ', 'class ', 'import ', 'from ')) or
                (in_code and (line.startswith('    ') or line.startswith('\t')))):
                in_code = True
                code_lines.append(line)
            elif in_code and not line.strip():
                code_lines.append(line)
            elif in_code and line.strip() and not line.startswith((' ', '\t')):
                break
        
        if code_lines:
            return '\n'.join(code_lines).strip()
        
        # Fallback: return the whole response
        return response
    
    def _clean_unified_diff(self, diff_text: str) -> str:
        """Clean unified diff text by removing all blank lines."""
        if not diff_text or not diff_text.strip():
            return ""
        
        lines = diff_text.split('\n')
        # Remove ALL blank lines - filter out any line that is empty or contains only whitespace
        cleaned_lines = [line for line in lines if line.strip()]
        
        return '\n'.join(cleaned_lines)

