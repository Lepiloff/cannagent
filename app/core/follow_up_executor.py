"""
Deterministic Follow-up Executor

Handles follow-up queries using deterministic logic instead of LLM.
This eliminates hallucinations by guaranteeing that only session strains
are used in responses.

Architecture:
1. LLM extracts structured intent (what user wants to do)
2. This executor performs the operation deterministically on session strains
3. Template-based response generation (no LLM hallucination possible)
"""

import logging
from typing import List, Tuple, Optional, Literal
from pydantic import BaseModel, Field
from app.models.database import Strain

logger = logging.getLogger(__name__)


class FollowUpIntent(BaseModel):
    """
    Structured intent for follow-up queries.

    Extracted by LLM but executed deterministically.
    This separation ensures no hallucinations in the final response.
    """
    action: Literal["compare", "filter", "sort", "select", "describe"] = Field(
        ...,
        description="Action to perform on session strains"
    )
    field: Optional[str] = Field(
        None,
        description="Field to operate on: thc, cbd, category, effects, negatives"
    )
    order: Optional[Literal["asc", "desc"]] = Field(
        None,
        description="Sort order for compare/sort actions"
    )
    filter_value: Optional[str] = Field(
        None,
        description="Value to filter by (e.g., 'Indica', 'high')"
    )
    strain_indices: Optional[List[int]] = Field(
        None,
        description="Specific strain indices for select action (0-based)"
    )


class FollowUpExecutor:
    """
    Deterministic executor for follow-up queries.

    Key principle: LLM determines WHAT to do (intent),
    Python code determines HOW to do it (execution).

    This guarantees:
    - Only session strains are used
    - No hallucinated strain names
    - Correct mathematical comparisons
    - Predictable, testable results
    """

    def execute(
        self,
        intent: FollowUpIntent,
        session_strains: List[Strain],
        language: str = "en"
    ) -> Tuple[List[Strain], str]:
        """
        Execute follow-up intent deterministically.

        Args:
            intent: Structured intent from LLM
            session_strains: Strains from previous query
            language: Response language (en/es)

        Returns:
            Tuple[result_strains, response_text]
            Both are guaranteed to use only session strains
        """
        if not session_strains:
            return self._no_strains_response(language)

        logger.info(f"Executing follow-up: action={intent.action}, field={intent.field}, order={intent.order}")

        if intent.action == "compare":
            return self._compare(intent, session_strains, language)
        elif intent.action == "sort":
            return self._sort(intent, session_strains, language)
        elif intent.action == "filter":
            return self._filter(intent, session_strains, language)
        elif intent.action == "select":
            return self._select(intent, session_strains, language)
        else:  # describe
            return self._describe(session_strains, language)

    def _compare(
        self,
        intent: FollowUpIntent,
        strains: List[Strain],
        language: str
    ) -> Tuple[List[Strain], str]:
        """
        Compare strains by field and return best match.

        Handles: "which has highest THC?", "which is strongest?", "lowest CBD?"
        """
        field = intent.field or "thc"
        order = intent.order or "desc"  # Default to highest

        # Get field value extractor
        def get_value(strain: Strain) -> float:
            if field == "thc":
                return float(strain.thc or 0)
            elif field == "cbd":
                return float(strain.cbd or 0)
            elif field == "cbg":
                return float(strain.cbg or 0)
            else:
                return 0

        # Sort strains
        sorted_strains = sorted(
            strains,
            key=get_value,
            reverse=(order == "desc")
        )

        # Get best match
        best = sorted_strains[0]
        best_value = get_value(best)

        # Generate response
        if language == "es":
            if order == "desc":
                metric_word = "más alto" if field in ["thc", "cbd", "cbg"] else "más fuerte"
            else:
                metric_word = "más bajo" if field in ["thc", "cbd", "cbg"] else "más suave"

            field_name = {"thc": "THC", "cbd": "CBD", "cbg": "CBG"}.get(field, field.upper())
            response = f"De la lista anterior, {best.name} tiene el {field_name} {metric_word} con {best_value:.1f}%."

            # Add runner-up if more than 1 strain
            if len(sorted_strains) > 1:
                second = sorted_strains[1]
                second_value = get_value(second)
                response += f" Le sigue {second.name} con {second_value:.1f}%."
        else:
            if order == "desc":
                metric_word = "highest" if field in ["thc", "cbd", "cbg"] else "strongest"
            else:
                metric_word = "lowest" if field in ["thc", "cbd", "cbg"] else "mildest"

            field_name = {"thc": "THC", "cbd": "CBD", "cbg": "CBG"}.get(field, field.upper())
            response = f"From the previous list, {best.name} has the {metric_word} {field_name} at {best_value:.1f}%."

            if len(sorted_strains) > 1:
                second = sorted_strains[1]
                second_value = get_value(second)
                response += f" {second.name} follows with {second_value:.1f}%."

        return sorted_strains, response

    def _sort(
        self,
        intent: FollowUpIntent,
        strains: List[Strain],
        language: str
    ) -> Tuple[List[Strain], str]:
        """
        Sort strains by field.

        Handles: "sort by THC", "order by CBD descending"
        """
        field = intent.field or "thc"
        order = intent.order or "desc"

        def get_value(strain: Strain) -> float:
            if field == "thc":
                return float(strain.thc or 0)
            elif field == "cbd":
                return float(strain.cbd or 0)
            elif field == "cbg":
                return float(strain.cbg or 0)
            else:
                return 0

        sorted_strains = sorted(
            strains,
            key=get_value,
            reverse=(order == "desc")
        )

        # Generate response
        field_name = {"thc": "THC", "cbd": "CBD", "cbg": "CBG"}.get(field, field.upper())
        strain_list = ", ".join([
            f"{s.name} ({get_value(s):.1f}%)"
            for s in sorted_strains[:3]
        ])

        if language == "es":
            order_word = "mayor a menor" if order == "desc" else "menor a mayor"
            response = f"Aquí están ordenadas por {field_name} de {order_word}: {strain_list}."
        else:
            order_word = "highest to lowest" if order == "desc" else "lowest to highest"
            response = f"Here they are sorted by {field_name} from {order_word}: {strain_list}."

        return sorted_strains, response

    def _filter(
        self,
        intent: FollowUpIntent,
        strains: List[Strain],
        language: str
    ) -> Tuple[List[Strain], str]:
        """
        Filter strains by category or attribute.

        Handles: "show only indica", "just the hybrids", "filter by sativa"
        """
        field = intent.field or "category"
        filter_value = intent.filter_value

        if not filter_value:
            return strains, self._generate_list_response(strains, language)

        # Normalize filter value
        filter_value_lower = filter_value.lower()

        if field == "category":
            # Filter by category
            filtered = [
                s for s in strains
                if s.category and s.category.lower() == filter_value_lower
            ]
        else:
            # For other fields, return all (not implemented yet)
            filtered = strains

        if not filtered:
            # No matches in session
            if language == "es":
                response = f"No hay cepas {filter_value} en la lista anterior. Las opciones disponibles son: {', '.join([s.name for s in strains])}."
            else:
                response = f"There are no {filter_value} strains in the previous list. Available options are: {', '.join([s.name for s in strains])}."
            return strains, response

        # Generate response
        names = ", ".join([s.name for s in filtered])
        if language == "es":
            if len(filtered) == 1:
                response = f"De la lista anterior, solo {names} es {filter_value}."
            else:
                response = f"De la lista anterior, las cepas {filter_value} son: {names}."
        else:
            if len(filtered) == 1:
                response = f"From the previous list, only {names} is a {filter_value}."
            else:
                response = f"From the previous list, the {filter_value} strains are: {names}."

        return filtered, response

    def _select(
        self,
        intent: FollowUpIntent,
        strains: List[Strain],
        language: str
    ) -> Tuple[List[Strain], str]:
        """
        Select specific strains by index or position.

        Handles: "the first one", "tell me about the second", "pick #3"
        """
        indices = intent.strain_indices or [0]

        # Validate indices
        valid_indices = [i for i in indices if 0 <= i < len(strains)]

        if not valid_indices:
            # Invalid selection, return all
            if language == "es":
                response = f"No encontré esa selección. Las opciones disponibles son: {', '.join([s.name for s in strains])}."
            else:
                response = f"I couldn't find that selection. Available options are: {', '.join([s.name for s in strains])}."
            return strains, response

        # Get selected strains
        selected = [strains[i] for i in valid_indices]

        # Generate response about selected strain(s)
        if len(selected) == 1:
            strain = selected[0]
            if language == "es":
                response = f"{strain.name} es una cepa {strain.category or 'desconocida'} con {strain.thc or 'N/A'}% de THC."
                if strain.cbd and float(strain.cbd) > 0:
                    response += f" También tiene {strain.cbd}% de CBD."
            else:
                response = f"{strain.name} is a {strain.category or 'unknown'} strain with {strain.thc or 'N/A'}% THC."
                if strain.cbd and float(strain.cbd) > 0:
                    response += f" It also has {strain.cbd}% CBD."
        else:
            names = ", ".join([s.name for s in selected])
            if language == "es":
                response = f"Has seleccionado: {names}."
            else:
                response = f"You've selected: {names}."

        return selected, response

    def _describe(
        self,
        strains: List[Strain],
        language: str
    ) -> Tuple[List[Strain], str]:
        """
        Describe the current strain list.

        Handles: "tell me about them", "what are these?", "describe the options"
        """
        return strains, self._generate_list_response(strains, language)

    def _generate_list_response(
        self,
        strains: List[Strain],
        language: str
    ) -> str:
        """Generate a descriptive response for a list of strains."""
        if not strains:
            return self._no_strains_response(language)[1]

        # Build strain summaries
        summaries = []
        for s in strains[:5]:  # Limit to 5
            thc_str = f"{s.thc}% THC" if s.thc else ""
            cbd_str = f"{s.cbd}% CBD" if s.cbd and float(s.cbd) > 0 else ""
            cannabinoids = ", ".join(filter(None, [thc_str, cbd_str]))
            summaries.append(f"{s.name} ({s.category or '?'}, {cannabinoids})")

        strain_list = "; ".join(summaries)

        if language == "es":
            response = f"Aquí tienes las opciones: {strain_list}."
        else:
            response = f"Here are your options: {strain_list}."

        return response

    def _no_strains_response(self, language: str) -> Tuple[List[Strain], str]:
        """Response when no session strains available."""
        if language == "es":
            response = "No hay cepas previas para comparar. ¿Te gustaría hacer una nueva búsqueda?"
        else:
            response = "There are no previous strains to compare. Would you like to start a new search?"

        return [], response


# Convenience function for intent detection keywords
def detect_follow_up_intent_keywords(query: str) -> Optional[FollowUpIntent]:
    """
    Rule-based fallback for follow-up intent detection.

    Used when LLM fails to extract intent or as validation.
    """
    query_lower = query.lower()

    # Compare patterns
    compare_highest = ["highest", "most", "strongest", "potent", "más alto", "más fuerte", "mayor"]
    compare_lowest = ["lowest", "least", "mildest", "weakest", "más bajo", "más suave", "menor"]

    # Field detection
    thc_keywords = ["thc", "potency", "potente", "fuerte", "strong"]
    cbd_keywords = ["cbd", "medical", "medicinal"]

    # Action detection
    if any(kw in query_lower for kw in compare_highest):
        field = "thc"
        if any(kw in query_lower for kw in cbd_keywords):
            field = "cbd"
        return FollowUpIntent(action="compare", field=field, order="desc")

    if any(kw in query_lower for kw in compare_lowest):
        field = "thc"
        if any(kw in query_lower for kw in cbd_keywords):
            field = "cbd"
        return FollowUpIntent(action="compare", field=field, order="asc")

    # Filter patterns
    filter_indica = ["indica", "only indica", "just indica", "solo indica"]
    filter_sativa = ["sativa", "only sativa", "just sativa", "solo sativa"]
    filter_hybrid = ["hybrid", "only hybrid", "just hybrid", "solo híbrido", "híbrido"]

    if any(kw in query_lower for kw in filter_indica):
        return FollowUpIntent(action="filter", field="category", filter_value="Indica")
    if any(kw in query_lower for kw in filter_sativa):
        return FollowUpIntent(action="filter", field="category", filter_value="Sativa")
    if any(kw in query_lower for kw in filter_hybrid):
        return FollowUpIntent(action="filter", field="category", filter_value="Hybrid")

    # Select patterns
    select_first = ["first one", "first", "primero", "primera", "#1"]
    select_second = ["second one", "second", "segundo", "segunda", "#2"]

    if any(kw in query_lower for kw in select_first):
        return FollowUpIntent(action="select", strain_indices=[0])
    if any(kw in query_lower for kw in select_second):
        return FollowUpIntent(action="select", strain_indices=[1])

    # Default to describe
    return FollowUpIntent(action="describe")
