from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import RoleAwareDefault
from apps.audit.services import record as audit

from .services import ReviewRefused, decide, kinds, pending_count, queue, review_info


class DecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["CONFIRMED", "REJECTED"])
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class QueueView(APIView):
    """Reviewers and administrators see every pending result; other users see their own."""

    permission_classes = [RoleAwareDefault]

    @extend_schema(parameters=[OpenApiParameter("decided", bool)], responses={200: dict})
    def get(self, request):
        decided = request.query_params.get("decided") in ("1", "true")
        return Response({"pending": pending_count(request.user), "results": queue(request.user, decided)})


class DecisionView(APIView):
    permission_classes = [RoleAwareDefault]

    @extend_schema(request=DecisionSerializer, responses={200: dict})
    def post(self, request, kind: str, pk: int):
        model = kinds().get(kind)
        record = model.objects.filter(pk=pk).first() if model else None
        if record is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        form = DecisionSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        try:
            decide(request.user, record, form.validated_data["decision"], form.validated_data["note"])
        except ReviewRefused as refused:
            return Response({"detail": str(refused)}, status=status.HTTP_403_FORBIDDEN
                            if "can't review" in str(refused) or "Only reviewers" in str(refused) else status.HTTP_400_BAD_REQUEST)
        # The note can quote the document, so it stays out of the audit log.
        audit(request, f"review.{record.review_state.lower()}", record, {"reference": record.reference, "kind": kind})
        return Response(review_info(record, request.user))
