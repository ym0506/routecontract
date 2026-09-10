import io.github.ym0506.routecontract.*;
public class ModuleBoundaryProbe {
 public static void main(String[] args) throws Exception {
  boolean[] action={false};
  try { RouteContract.capture("migration.module",()->{action[0]=true;});throw new AssertionError("unexpected success"); }
  catch(IllegalStateException e) {if(!e.getMessage().contains("RC_UNSUPPORTED_MODULE_PATH")||action[0])throw e;System.out.println("RC_UNSUPPORTED_MODULE_PATH; action=false");}
 }
}
