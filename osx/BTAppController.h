/* BTAppController */

#import <Cocoa/Cocoa.h>

@interface BTAppController : NSObject
{
    IBOutlet NSTextField *url;
    IBOutlet NSWindow *urlWindow;
    int dlid;
    NSMutableArray *dlControllers;
}
- (void)awakeFromNib;
- (IBAction)cancelUrl:(id)sender;
- (IBAction)openURL:(id)sender;
- (IBAction)openTrackerResponse:(id)sender;
- (IBAction)takeUrl:(id)sender;
- (void)runWithFile:(NSString *)filename;
- (void)runWithUrl:(NSString *)url;
- (void)cancelDlWithId:(NSNumber *)dlid;
// application delegate messages
- (BOOL)application:(NSApplication *)theApplication openFile:(NSString *)filename;
@end