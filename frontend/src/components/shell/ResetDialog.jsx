import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "../ui/alert-dialog";
import { useStore } from "../../store/useStore";
import { dispatchService } from "../../services";

export function ResetDialog() {
  const open = useStore((s) => s.transient.resetOpen);
  const setTransient = useStore((s) => s.setTransient);
  return (
    <AlertDialog open={open} onOpenChange={(v) => setTransient({ resetOpen: v })}>
      <AlertDialogContent className="rounded-[24px] border-white/90 bg-white/95 backdrop-blur-xl" data-testid="reset-demo-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>Reset the demo?</AlertDialogTitle>
          <AlertDialogDescription>
            Restores the initial scenario, the clock (Mon 26 Oct · 10:00 PT), metrics and all records. Current progress is discarded.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel data-testid="reset-demo-cancel" className="rounded-xl">Cancel</AlertDialogCancel>
          <AlertDialogAction data-testid="reset-demo-confirm" className="rounded-xl bg-[#181A1A] hover:bg-[#2a2d2d]" onClick={() => dispatchService.resetDemo()}>
            Reset demo
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
