import io.github.ym0506.routecontract.manifest.ManifestDiffCode;
public class LegacyEnumSwitchProbe {
 static String label(ManifestDiffCode code) { return switch(code) {
 case MATCH -> "MATCH";
 case UNSUPPORTED_SCHEMA -> "UNSUPPORTED_SCHEMA";
 case OPERATION_ID_MISMATCH -> "OPERATION_ID_MISMATCH";
 case APPROVED_MANIFEST_NOT_ELIGIBLE -> "APPROVED_MANIFEST_NOT_ELIGIBLE";
 case CAPTURE_INCOMPLETE -> "CAPTURE_INCOMPLETE";
 case CALLBACK_FAILURE_NOT_ELIGIBLE -> "CALLBACK_FAILURE_NOT_ELIGIBLE";
 case ATTEMPT_BUDGET_EXCEEDED -> "ATTEMPT_BUDGET_EXCEEDED";
 case DATA_SOURCE_BUDGET_EXCEEDED -> "DATA_SOURCE_BUDGET_EXCEEDED";
 case POLICY_CHANGED -> "POLICY_CHANGED";
 case STRUCTURAL_ATTEMPT_REMOVED -> "STRUCTURAL_ATTEMPT_REMOVED";
 case STRUCTURAL_ATTEMPT_ADDED -> "STRUCTURAL_ATTEMPT_ADDED";
 case OBSERVED_ATTEMPT_COUNT_CHANGED -> "OBSERVED_ATTEMPT_COUNT_CHANGED";
 case OBSERVED_DATA_SOURCE_SET_CHANGED -> "OBSERVED_DATA_SOURCE_SET_CHANGED";
 case OUTCOME_COUNTS_CHANGED -> "OUTCOME_COUNTS_CHANGED";
 }; }
 public static void main(String[] args) {
   if(args.length>0 && !args[0].equals("old-values")) {
     System.out.println(label(ManifestDiffCode.valueOf(args[0]))); return;
   }
   for(ManifestDiffCode code:ManifestDiffCode.values()) {
     if(args.length>0 && (code.name().equals("UNSUPPORTED_RUNTIME_IDENTITY")||code.name().equals("RUNTIME_IDENTITY_MISMATCH")))continue;
     String mapped=label(code);
     if(!mapped.equals(code.name()))throw new AssertionError("old mapping changed");
     System.out.println(mapped);
   }
 }
}
