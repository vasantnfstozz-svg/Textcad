"""Run a command inside a Windows Job object with a hard memory ceiling.

    python probes/memcap.py --gb 6 --timeout 600 -- python tests/journeys.py ...

The kernel refuses commits past the ceiling, so an OpenCASCADE op that would
eat the box gets std::bad_alloc / MemoryError instead of taking the laptop
down (2026-09-12: one plate add reached 44 GB on a 16 GB machine and the
machine died). A --timeout kills the whole job too.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x200
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in
                ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                 "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", wt.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wt.LARGE_INTEGER),
                ("LimitFlags", wt.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wt.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wt.DWORD),
                ("SchedulingClass", wt.DWORD)]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


def make_job(limit_bytes: int):
    job = k32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_JOB_MEMORY | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    info.JobMemoryLimit = limit_bytes
    if not k32.SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                       ctypes.byref(info), ctypes.sizeof(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    return job


def peak(job) -> int:
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    k32.QueryInformationJobObject(job, JobObjectExtendedLimitInformation,
                                  ctypes.byref(info), ctypes.sizeof(info), None)
    return int(info.PeakJobMemoryUsed)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--gb", type=float, default=6)
    p.add_argument("--timeout", type=float, default=600)
    p.add_argument("cmd", nargs=argparse.REMAINDER)
    a = p.parse_args()
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    job = make_job(int(a.gb * 1024 ** 3))
    CREATE_SUSPENDED = 0x4
    proc = subprocess.Popen(cmd, creationflags=CREATE_SUSPENDED)
    if not k32.AssignProcessToJobObject(job, wt.HANDLE(proc._handle)):
        proc.kill()
        raise ctypes.WinError(ctypes.get_last_error())
    # resume the main thread
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess(wt.HANDLE(proc._handle))
    t0 = time.time()
    try:
        code = proc.wait(timeout=a.timeout)
        why = f"exit {code} (0x{code & 0xFFFFFFFF:08X})"
    except subprocess.TimeoutExpired:
        k32.TerminateJobObject(job, 124)
        code, why = 124, f"TIMEOUT after {a.timeout}s, job killed"
    print(f"[memcap] {why}; {time.time() - t0:.0f}s; peak job memory {peak(job) / 1024 ** 3:.2f} GB "
          f"(cap {a.gb} GB)", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
