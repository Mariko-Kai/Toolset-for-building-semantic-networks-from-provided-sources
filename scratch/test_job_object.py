import os
import sys
import time
import subprocess
import ctypes
from ctypes import wintypes

# Windows Job Object structures and constants
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9

class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
        ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_void_p),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]

class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]

class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]

def main():
    if os.name != 'nt':
        print("This script is only for Windows.")
        return

    # Start a notepad process as a test
    cmd = ["notepad.exe"]
    print("Starting notepad...")
    process = subprocess.Popen(cmd)
    print(f"Notepad started. PID: {process.pid}, HANDLE: {int(process._handle)}")

    try:
        # Create Job Object
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        
        # Declare signatures for 64-bit safety
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        hJob = kernel32.CreateJobObjectW(None, None)
        if not hJob:
            raise ctypes.WinError(ctypes.get_last_error())
        
        print(f"Job Object created. Handle: {hJob}")

        # Set limit info: kill on close
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        
        res = kernel32.SetInformationJobObject(
            hJob,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info)
        )
        if not res:
            raise ctypes.WinError(ctypes.get_last_error())
        
        print("Extended limit information set successfully (kill on close).")

        # Assign process to job
        res = kernel32.AssignProcessToJobObject(hJob, int(process._handle))
        if not res:
            raise ctypes.WinError(ctypes.get_last_error())
            
        print("Process assigned to Job Object successfully.")
        
        print("Waiting 5 seconds, notepad should be open. Then we will close the job handle.")
        time.sleep(5)
        
        print("Closing Job Object handle...")
        kernel32.CloseHandle(hJob)
        print("Job handle closed. Notepad should have terminated.")
        
        # Check if notepad is still running
        time.sleep(1)
        poll = process.poll()
        if poll is None:
            print("Warning: Notepad is still running!")
        else:
            print(f"Success: Notepad terminated with exit code: {poll}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        # Cleanup notepad if anything failed
        if process.poll() is None:
            process.terminate()

if __name__ == '__main__':
    main()
